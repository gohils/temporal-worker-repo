# -----------------------------
# direct_debit_worker_v2.py
# -----------------------------

import asyncio, json, uuid, os
from dataclasses import dataclass
from datetime import timedelta
from typing import Dict, Any, Optional

from temporalio import workflow, activity
from temporalio.client import Client
from temporalio.worker import Worker
from temporalio.common import RetryPolicy

# -----------------------------
# SAFE IMPORTS
# -----------------------------
with workflow.unsafe.imports_passed_through():
    import httpx
    from ai_worker_db_log import (
        log_activity,
        upsert_workflow_instance,
        store_ocr_result,
        store_erp_document,
        log_approval_signal,
    )
    from salesforce_dd_utils import (upsert_account_with_direct_debit)

# -----------------------------
# CONFIG
# -----------------------------
TEMPORAL_HOST = os.getenv("TEMPORAL_HOST", "temporal-server-demo.australiaeast.cloudapp.azure.com:7233")
TASK_QUEUE = os.getenv("TASK_QUEUE", "direct-debit-queue")
AI_API_URL = os.getenv("AI_API_URL", "https://zdoc-ai-api.azurewebsites.net")
# TASK_QUEUE = "direct-debit-queue"
# AI_API_URL = os.getenv("AI_API_URL", "http://localhost:8000")

# -----------------------------
# CONTRACTS
# -----------------------------
@dataclass
class ActivityInput:
    payload: Dict[str, Any]
    context: Dict[str, Any]

@dataclass
class ActivityOutput:
    response: Dict[str, Any]
    context: Dict[str, Any]

# =========================================================
# CONTEXT HELPERS (IDENTICAL TO INVOICE)
# =========================================================
def build_base_context(payload, wf_id):
    return {
        "workflow_id": wf_id,
        "workflow_type": payload.get("workflow_type"),
        "reference_id": payload.get("reference_id"),
        "header_id": payload.get("header_id"),
    }

def merge_context(parent, child):
    return {
        **parent,
        **child,
        "workflow_id": parent.get("workflow_id"),
        "workflow_type": parent.get("workflow_type"),
        "reference_id": parent.get("reference_id"),
        "header_id": parent.get("header_id"),
        "item_id": child.get("item_id") or parent.get("item_id"),
        "doc_type": child.get("doc_type") or parent.get("doc_type"),
    }

# =========================================================
# EXECUTION WRAPPER (FULL PARITY)
# =========================================================
async def execute_step(activity_fn, payload, context, step, timeout=30):

    prev_node = context.get("current_node_id")

    context = {
        **context,
        "prev_node_id": prev_node,
        "current_node_id": step,
        "branch_id": context.get("branch_id", "MAIN"),
    }

    result: ActivityOutput = await workflow.execute_activity(
        activity_fn,
        ActivityInput(payload, context),
        start_to_close_timeout=timedelta(seconds=timeout),
        retry_policy=RetryPolicy(maximum_attempts=3),
    )

    payload = {**payload, **result.response}

    business_context = merge_context(context, result.context)

    # 🔒 Preserve graph state
    business_context["prev_node_id"] = context["prev_node_id"]
    business_context["current_node_id"] = context["current_node_id"]
    business_context["branch_id"] = context["branch_id"]

    return payload, business_context

# =========================================================
# 01 PREPROCESS
# =========================================================
@activity.defn
@log_activity(display_name="01_PREPROCESS")
async def preprocess(input: ActivityInput) -> ActivityOutput:

    items = input.payload.get("items", [])
    if not items:
        raise ValueError("No items found")

    normalized = []
    for item in items:
        doc_url = item.get("document_url") or item.get("input_parameters", {}).get("document_url")

        normalized.append({
            "item_id": str(item.get("item_id") or item.get("id") or uuid.uuid4()),
            "document_url": doc_url,
            "doc_type": item.get("doc_type") or "direct_debit",
        })

    upsert_workflow_instance(
        workflow_id=input.context["workflow_id"],
        workflow_type=input.context["workflow_type"],
        status="STARTED",
        input_data=input.payload,
        header_id=input.context.get("header_id"),
        reference_id=input.context.get("reference_id"),
    )

    return ActivityOutput(
        {**input.payload, "normalized_items": normalized},
        {"preprocess": {"count": len(normalized)}}
    )

# =========================================================
# 02 OCR
# =========================================================
@activity.defn
@log_activity(display_name="02_OCR")
async def ocr(input: ActivityInput) -> ActivityOutput:

    # print(f"Performing OCR for document input.payload : {input.payload}")
    # print(f"Performing OCR for document input.payload : {input.context}")
    doc_url = input.payload.get("document_url")

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(
            f"{AI_API_URL}/ai_doc/analyse_directdebit",
            params={"url": doc_url},
        )
        resp.raise_for_status()
        ocr_data = resp.json()

    print(f"=============== OCR Result: {ocr_data}")
    document_id = store_ocr_result(
        workflow_id=input.context.get("workflow_id"),
        header_id=input.context.get("header_id"),
        item_id=input.context.get("item_id"),
        document_url=doc_url,
        doc_type=input.context.get("doc_type", "direct_debit)"),
        ocr_raw=json.dumps(ocr_data),
        ocr_result=ocr_data,
        extracted_fields=ocr_data,
        status="OCR_COMPLETE",
    )

    return ActivityOutput(
        {"document_id": document_id, "ocr_data": ocr_data},  # return OCR data
        {"last_ocr": {"document_id": document_id}},          # update context
    )


# =========================================================
# 03 VALIDATE
# =========================================================
@activity.defn
@log_activity(display_name="03_VALIDATE")
async def validate(input: ActivityInput) -> ActivityOutput:

    form = input.payload.get("ocr_data", {})
    errors = []

    if not form.get("AccountNumber"):
        errors.append("ACCOUNT_MISSING")

    if not form.get("BSBNumber"):
        errors.append("INVALID_BSB")

    status = "VALID" if not errors else "INVALID"

    return ActivityOutput(
        {**input.payload, "validation": {"status": status, "errors": errors}},
        {"validate": {"status": status}}
    )

# =========================================================
# 04 RISK
# =========================================================
@activity.defn
@log_activity(display_name="04_RISK")
async def risk(input: ActivityInput) -> ActivityOutput:

    form = input.payload.get("ocr_data", {})
    validation = input.payload.get("validation", {})

    score = 0.0
    reasons = []

    if validation.get("status") == "INVALID":
        score += 0.6
        reasons.append("INVALID_FORM")

    if form.get("AccountNumber") == "99999999":
        score += 0.7
        reasons.append("SUSPICIOUS_ACCOUNT")

    level = "HIGH" if score > 0.6 else "LOW"

    return ActivityOutput(
        {**input.payload, "risk": {"score": score, "level": level, "reasons": reasons}},
        {"risk": {"level": level}}
    )

# =========================================================
# 05 DECISION
# =========================================================
@activity.defn
@log_activity(display_name="05_DECISION")
async def decision(input: ActivityInput) -> ActivityOutput:

    validation = input.payload.get("validation", {}).get("status")
    risk_level = input.payload.get("risk", {}).get("level")

    decision = "auto_approve" if validation == "VALID" and risk_level != "HIGH" else "manual_review"

    return ActivityOutput(
        {**input.payload, "approval_decision": decision},
        {"decision": {"type": decision}}
    )

# =========================================================
# 06 ERP
# =========================================================
@activity.defn
@log_activity(display_name="06_CREATE_MANDATE")
async def create_mandate(input: ActivityInput) -> ActivityOutput:

    mandate_id = f"MANDATE-{uuid.uuid4().hex[:8]}"

    store_erp_document(
        doc_id=mandate_id,
        doc_type="direct_debit",
        workflow_id=input.context.get("workflow_id"),
        header_id=input.context.get("header_id"),
        item_id=input.context.get("item_id"),
        header_data=input.payload,
        approval_status="APPROVED",
        approved_by="SYSTEM",
        reference_id=input.context.get("reference_id"),
    )

    return ActivityOutput(
        {**input.payload, "mandate_id": mandate_id},
        {"erp": {"id": mandate_id}}
    )

# =========================================================
# 07 NOTIFY
# =========================================================
@activity.defn
@log_activity(display_name="07_NOTIFY")
async def notify(input: ActivityInput) -> ActivityOutput:
    return ActivityOutput(
        {**input.payload, "notification": "sent"},
        {"notify": {"status": "sent"}}
    )


# =========================================================
# 08 AUDIT
# =========================================================
@activity.defn
@log_activity(display_name="08_AUDIT")
async def audit(input: ActivityInput) -> ActivityOutput:
    print(json.dumps(input.payload, indent=2))
    return ActivityOutput({**input.payload, "status": "stored"}, {})

@activity.defn
@log_activity(display_name="09_SALESFORCE_SYNC", activity_group="SYSTEM")
async def salesforce_sync(input: ActivityInput) -> ActivityOutput:

    header_id = input.context.get("header_id")

    try:
        result = upsert_account_with_direct_debit(header_id)

        return ActivityOutput(
            {"status": "SUCCESS", "salesforce_result": result},
            {"salesforce": {"status": "SUCCESS"}}
        )

    except Exception as e:

        return ActivityOutput(
            {"status": "SKIPPED", "reason": str(e)},
            {"salesforce": {"status": "SKIPPED"}}
        )
    

# =========================================================
# WORKFLOW (FULL PARITY)
# =========================================================
@workflow.defn
class DirectDebitWorkflow:

    def __init__(self):
        self.manual_approval_decision: Optional[str] = None
        self.manual_approval_details: Optional[Dict[str, Any]] = None

    @workflow.signal(name="manual_approval")
    def manual_approve(self, approval_details: Dict[str, Any]):
        self.manual_approval_decision = approval_details.get("decision", "REJECTED").upper()
        self.manual_approval_details = approval_details

    @workflow.run
    async def run(self, initial_payload: Dict):

        wf_id = workflow.info().workflow_id
        context = build_base_context(initial_payload, wf_id)
        payload = initial_payload.copy()

        payload, context = await execute_step(preprocess, payload, context, "01_PREPROCESS")

        results = []

        item = payload.get("normalized_items", [])[0]

        item_payload = {**payload, **item}

        item_context = merge_context(context, {
            "item_id": item["item_id"],
            "doc_type": item.get("doc_type"),
        })

        item_payload, item_context = await execute_step(ocr, item_payload, item_context, "02_OCR", 120)
        item_payload, item_context = await execute_step(validate, item_payload, item_context, "03_VALIDATE")
        item_payload, item_context = await execute_step(risk, item_payload, item_context, "04_RISK")
        item_payload, item_context = await execute_step(decision, item_payload, item_context, "05_DECISION")

        decision_val = item_payload.get("approval_decision")

        log_approval_signal(
            workflow_id=wf_id,
            workflow_type=context.get("workflow_type"),
            reference_id=context.get("reference_id"),
            header_id=context.get("header_id"),
            item_id=item["item_id"],
            task_name="MANDATE_APPROVAL",
            task_type="MANDATE_APPROVAL_L1",
            approval_signal_name="SYSTEM" if decision_val.startswith("auto") else "manual_approval",
            assigned_role="FINANCE_APPROVER",
            status="PENDING" if decision_val == "manual_review" else "COMPLETED",
            decision="AUTO_APPROVED" if decision_val.startswith("auto") else None,
            task_approval_summary={
                "Bank_account_number": item_payload.get("ocr_data", {}).get("AccountNumber"),
                "Bank_account_name": item_payload.get("ocr_data", {}).get("AccountName"),
                "approval_decision": decision_val
            },
            signal_payload={"source": "SYSTEM"}
        )

        if decision_val == "manual_review":

            await workflow.wait_condition(
                lambda: self.manual_approval_decision is not None,
                timeout=timedelta(minutes=30)
            )

            manual = self.manual_approval_details or {}
            final_decision = "approved" if manual.get("decision", "").upper() == "APPROVED" else "rejected"

            item_payload["approval_decision"] = final_decision

        decision_val = item_payload.get("approval_decision")
        item_context["branch_id"] = decision_val.upper()

        if decision_val in ["auto_approve", "approved"]:
            item_payload, item_context = await execute_step(create_mandate, item_payload, item_context, "06_ERP")
        else:
            item_payload, item_context = await execute_step(notify, item_payload, item_context, "07_NOTIFY")

        results.append({**item_payload, "context": item_context})

        item_payload, item_context = await execute_step(audit, {"results": results}, item_context, "08_AUDIT")

        item_payload, item_context = await execute_step(
            salesforce_sync,
            {"documents": results},
            item_context,
            "09_SALESFORCE_SYNC"
        )

        upsert_workflow_instance(
            workflow_id=wf_id,
            workflow_type=payload.get("workflow_type"),
            status="COMPLETED",
            input_data=payload,
            header_id=payload.get("header_id"),
            reference_id=payload.get("reference_id"),
            end_time=workflow.now()
        )

        return {"status": "COMPLETED", "results": results}

# =========================================================
# WORKER
# =========================================================
async def main():

    client = await Client.connect(TEMPORAL_HOST)

    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[DirectDebitWorkflow],
        activities=[
            preprocess,
            ocr,
            validate,
            risk,
            decision,
            create_mandate,
            notify,
            audit,
            salesforce_sync
        ],
    )

    async with worker:
        print("🚀 Direct Debit Worker (V2 - FULL PARITY)")
        await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())