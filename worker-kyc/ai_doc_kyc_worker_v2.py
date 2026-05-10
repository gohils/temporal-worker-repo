# -----------------------------
# customer_onboarding_hybrid.py
# -----------------------------

import asyncio, json, uuid, os
from dataclasses import dataclass
from datetime import timedelta, datetime
from typing import Dict, Any

from temporalio import workflow, activity
from temporalio.client import Client
from temporalio.worker import Worker
from temporalio.common import RetryPolicy

# Safe imports (allowed inside workflow sandbox)
with workflow.unsafe.imports_passed_through():
    import httpx
    from ai_worker_db_log import (
        log_activity,
        upsert_workflow_instance,
        store_ocr_result,
        store_erp_document,
        log_approval_signal,
    )

# Environment configs
TEMPORAL_HOST = os.getenv("TEMPORAL_HOST", "temporal-server-demo.australiaeast.cloudapp.azure.com:7233")
TASK_QUEUE = "kyc-onboarding-queue"
AI_API_URL = os.getenv("AI_API_URL", "https://zdoc-ai-api.azurewebsites.net")  # AI endpoint

# -----------------------------
# Approval logging helper
# -----------------------------
def log_wf_approval(
    wf_id, wf_type,reference_id,header_id,item_id, status, signal_name=None, decision=None,
    role=None, user=None, task_approval_summary=None, comments=None, additional_data=None
):
    log_approval_signal(
        workflow_id=wf_id,
        workflow_type=wf_type,
        reference_id=reference_id,
        header_id=header_id,
        item_id=item_id,
        task_name="DOCUMENT_APPROVAL",
        task_type="DOCUMENT_APPROVAL_L1",
        approval_signal_name=signal_name,
        assigned_role=role,
        action_by=user,
        status=status,
        decision=decision,
        comments=comments,
        additional_data=additional_data,
        task_approval_summary=task_approval_summary
    )
    print(f"📝 [APPROVAL LOGGED] status={status}, decision={decision}, role={role}, user={user}")

# -----------------------------
# Context Management (CORE)
# -----------------------------
def build_base_context(payload, wf_id):
    # Build initial workflow context
    return {
        "workflow_id": wf_id,
        "workflow_type": payload.get("workflow_type"),
        "reference_id": payload.get("reference_id"),
        "header_id": payload.get("header_id"),
    }

def merge_context(parent, child):
    # Merge parent and child context with item fallback
    return {
        **parent,
        **child,
        "workflow_id": parent.get("workflow_id"),
        "workflow_type": parent.get("workflow_type"),
        "reference_id": parent.get("reference_id"),
        "header_id": parent.get("header_id"),
        "item_id": child.get("item_id") or parent.get("item_id"),
        "doc_type": child.get("doc_type") or parent.get("doc_type"),
    # IMPORTANT CHANGE (implicit fix):
    # prev_node_id / current_node_id are NOT allowed to be overwritten by child
    }

# -----------------------------
# Execution Wrapper
# -----------------------------
async def execute_step(activity_fn, payload, context, step, timeout=30):

    # -----------------------------
    # GRAPH STATE (ONLY PLACE WHERE IT IS UPDATED)
    # -----------------------------
    prev_node = context.get("current_node_id")

    context = {
        **context,
        "prev_node_id": prev_node,
        "current_node_id": step,
        "branch_id": context.get("branch_id")
    }

    result: ActivityOutput = await workflow.execute_activity(
        activity_fn,
        ActivityInput(payload, context),
        start_to_close_timeout=timedelta(seconds=timeout),
        retry_policy=RetryPolicy(maximum_attempts=3),
    )

    payload = {**payload, **result.response}

    # -----------------------------
    # SAFE MERGE (DO NOT OVERWRITE GRAPH STATE)
    # -----------------------------
    business_context = merge_context(context, result.context)

    # preserve graph fields explicitly
    business_context["prev_node_id"] = context["prev_node_id"]
    business_context["current_node_id"] = context["current_node_id"]
    business_context["branch_id"] = context["branch_id"]

    return payload, business_context

# -----------------------------
# Data Contracts
# -----------------------------

@dataclass
class ActivityInput:
    """Activity input wrapper"""
    payload: Dict[str, Any]
    context: Dict[str, Any]

@dataclass
class ActivityOutput:
    """Activity output wrapper"""
    response: Dict[str, Any]
    context: Dict[str, Any]

# -----------------------------
# Activities
# -----------------------------

@activity.defn
@log_activity(display_name="01_PREPROCESS", activity_group="SYSTEM")
async def pre_process_documents(input: ActivityInput) -> ActivityOutput:
    """Preprocess and normalize incoming documents (lossless version)"""

    # print("📄 [PREPROCESS] Starting preprocessing", input.payload, input.context)

    params = input.payload or {}
    documents = params.get("items", [])

    if not documents:
        raise ValueError("Missing documents")

    normalized_docs = []

    for doc in documents:

        # -----------------------------
        # SAFE EXTRACTION (NO LOSS)
        # -----------------------------
        input_params = doc.get("input_parameters", {}) or {}
        declared_data = doc.get("declared_data", {}) or {}

        normalized_doc = {
            # keep original identity
            "item_id": doc.get("item_id"),  # FIXED (was doc.get("id"))

            # preserve full traceability
            "doc_id": str(uuid.uuid4())[:8],

            # business metadata
            "declared_doc_type": declared_data.get("document_type") or doc.get("doc_type"),

            # CRITICAL FIELD (FIXED PATH)
            "document_url": input_params.get("document_url"),

            # keep original structure for downstream safety
            "raw": doc,
        }

        # validation guard (fail early, not downstream)
        if not normalized_doc["document_url"]:
            raise ValueError(f"Missing document_url for item_id={normalized_doc['item_id']}")

        normalized_docs.append(normalized_doc)

    # -----------------------------
    # PERSIST WORKFLOW START
    # -----------------------------
    upsert_workflow_instance(
        workflow_id=input.context["workflow_id"],
        workflow_type=input.context["workflow_type"],
        status="STARTED",
        input_data=params,
        header_id=params.get("header_id"),
        reference_id=params.get("reference_id"),
    )

    # -----------------------------
    # RETURN LOSSLESS CONTRACT
    # -----------------------------
    return ActivityOutput(
        {
            "normalized_documents": normalized_docs,
            # optional convenience alias (safe for old consumers)
            "items_count": len(normalized_docs),
        },
        {
            "preprocessed_at": str(datetime.utcnow()),
        },
    )

@activity.defn
@log_activity(display_name="02_CLASSIFY", activity_group="AI")
async def ai_classify_document(input: ActivityInput) -> ActivityOutput:
    """Classify document type via AI service"""
    # print("📄 [AI_CLASSIFY] Starting document classification", input.payload, input.context)

    async with httpx.AsyncClient(timeout=30) as client:
        result = (await client.get(
            f"{AI_API_URL}/ai_doc/classify_document",
            params={"url": input.payload["document_url"]},
        )).json()

    return ActivityOutput(
        {
            "doc_type": result.get("doc_type"),
            "confidence": result.get("confidence_pct", 0),
        },
        {"last_classification": result},  # store classification metadata
    )

@activity.defn
@log_activity(display_name="03_OCR", activity_group="AI")
async def ai_process_doc(input: ActivityInput) -> ActivityOutput:
    """Perform OCR on document using AI service"""
    # print("📄 [AI_OCR] Starting OCR processing", input.payload, input.context)
    doc_url = input.payload.get("document_url")
    doc_type = input.payload.get("doc_type", "generic_document")

    model_map = {
        "passport": "analyse_passport",
        "driving_licence": "analyse_licence",
        "electricity_bill": "analyse_electricity",
    }
    model_name = model_map.get(doc_type.lower(), "analyse_document")

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{AI_API_URL}/ai_doc/{model_name}",
            params={"url": doc_url},
        )
        resp.raise_for_status()
        ocr_data = resp.json()

    document_id = store_ocr_result(
        workflow_id=input.context.get("workflow_id"),
        header_id=input.context.get("header_id"),
        item_id=input.context.get("item_id"),
        document_url=doc_url,
        doc_type=doc_type,
        ocr_raw=json.dumps(ocr_data),
        ocr_result=ocr_data,
        extracted_fields=ocr_data,
        status="OCR_COMPLETE",
    )

    return ActivityOutput(
        {"document_id": document_id, "ocr_data": ocr_data},  # return OCR data
        {"last_ocr": {"document_id": document_id}},          # update context
    )

@activity.defn
@log_activity(display_name="04_VALIDATE", activity_group="VALIDATION")
async def validate_document(input: ActivityInput) -> ActivityOutput:
    """Validate OCR result"""
    status = "VALID" if input.payload.get("ocr_data") else "INVALID"
    return ActivityOutput(
        {"validation_status": status},   # return validation result
        {"last_validation": status},     # update context
    )

@activity.defn
@log_activity(display_name="05_CROSS_VERIFY", activity_group="VALIDATION")
async def cross_document_verification(input: ActivityInput) -> ActivityOutput:
    """Stub for cross-document verification"""
    docs = input.payload.get("documents", [])
    passport = next((d for d in docs if d.get("doc_type") == "passport"), None)
    license = next((d for d in docs if d.get("doc_type") == "driving_licence"), None)
    utility_bill = next((d for d in docs if d.get("doc_type") == "utility_bill"), None)

    missing = []

    # if not license:
    #     missing.append("driving_licence")

    # if not passport:
    #     missing.append("passport")

    # if not utility_bill:
    #     missing.append("proof_of_address")


    cross_verification_decision = "AUTO_APPROVED" if not missing else "MANUAL_REVIEW"

    return ActivityOutput(
        {   "decision": cross_verification_decision,
            "missing_documents": missing,
            "documents": docs
        },
        {}
    )


@activity.defn
@log_activity(display_name="06_ERP_POST", activity_group="ERP")
async def post_to_erp(input: ActivityInput) -> ActivityOutput:
    """Store document into ERP system"""
    erp_id = f"ERP-{uuid.uuid4().hex[:8]}"  # generate ERP id

    workflow_id = input.context.get("workflow_id")
    child_workflow_id = input.context.get("child_workflow_id")
    header_id = input.context.get("header_id")
    item_id = input.context.get("item_id")
    reference_id = input.context.get("reference_id")
    doc_type = input.context.get("doc_type") or input.payload.get("doc_type") or "generic_document"

    store_erp_document(
        doc_id=erp_id,
        doc_type=doc_type,
        workflow_id=workflow_id,
        child_workflow_id=child_workflow_id,
        header_id=header_id,
        item_id=item_id,
        header_data=input.payload,
        line_items=[],  # extendable
        approval_status="APPROVED",
        approved_by="SYSTEM",
        doc_date=str(datetime.utcnow().date()),
        owner_name="SYSTEM",
        reference_id=reference_id,
    )

    return ActivityOutput({"erp_id": erp_id}, {})

@activity.defn
@log_activity(display_name="07_AUDIT", activity_group="SYSTEM")
async def store_audit(input: ActivityInput) -> ActivityOutput:
    """Store workflow audit logs"""
    print(json.dumps(input.payload, indent=2))  # print audit log
    return ActivityOutput({"status": "stored"}, {})  # confirm audit
# -----------------------------
# Add a human-readable formatter for KYC summary
@activity.defn
@log_activity(display_name="approval_decision")
async def approval_decision(input: ActivityInput) -> ActivityOutput:
    """Determine and log approval decision"""
    wf_id = input.context.get("workflow_id")
    wf_type = input.context.get("workflow_type")
    header_id = input.context.get("header_id")
    reference_id = input.context.get("reference_id")
    decision = input.payload.get("decision", "REVIEW_REQUIRED")
    docs = input.payload.get("documents", [])
    missing = input.payload.get("missing_documents", [])

    summary = {
        "documents": [
            {
                "document_type": d.get("doc_type"),
                "status": d.get("document_validation_status"),
                "confidence": d.get("summary", {}).get("confidence", 0),
            }
            for d in docs
        ],
        "overall_status": decision,
        "missing_documents": missing
    }

    documents_summary = [
        f"{d.get('doc_type', 'Unknown')} was {d.get('document_validation_status', 'UNKNOWN')}"
        for d in docs
    ]

    documents_text = ". ".join(documents_summary)

    documents_sentence = (
        f"{documents_text}. "
        f"Total {len(docs)} document(s) were evaluated for this request {reference_id}."
    )

    task_summary = {
        "overall_decision": decision,
        "documents_received": len(docs),
        "document_verification": documents_sentence
    }

    if decision == "AUTO_APPROVED":
        log_wf_approval(
            wf_id=wf_id, wf_type=wf_type, reference_id=input.context.get("reference_id"), header_id=header_id, item_id=None, status="COMPLETED", signal_name="SYSTEM",
            decision="AUTO_APPROVED", role="SYSTEM", user="SYSTEM",
            comments="auto-approved", additional_data=summary, task_approval_summary=task_summary
        )
        print(f"✅ [APPROVAL DECISION] document {header_id} auto-approved")
    else:
        log_wf_approval(
            wf_id=wf_id, wf_type=wf_type, reference_id=input.context.get("reference_id"),header_id=header_id, item_id=None, status="PENDING", signal_name="manual_approval",
            decision=None, role="MANAGER", user=None,
            comments="manual review required", additional_data=summary, task_approval_summary=task_summary
        )
        print(f"⏳ [APPROVAL DECISION] document {header_id} requires manual review")

    payload = {**input.payload, "approval_decision": decision}
    context = {**input.context, "approval_decision": decision}
    return ActivityOutput(payload, context)

# -----------------------------
# Child Workflow
# -----------------------------
@workflow.defn
class DocumentWorkflow:
    @workflow.run
    async def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process individual document"""
        data = payload["data"]
        context = payload["context"]
        result = {
            "doc_id": data.get("doc_id"),
            "doc_type": "UNKNOWN",
            "ocr_data": None,
            "validation": "FAILED",
            "status": "FAILED",
            "errors": [],
            "erp_id": None,
        }

        try:
            # 1️⃣ Classify
            data, context = await execute_step(ai_classify_document, data, context, "02_CLASSIFY")
            result["doc_type"] = data.get("doc_type")

            # 2️⃣ OCR
            data, context = await execute_step(ai_process_doc, data, context, "03_OCR")
            result["ocr_data"] = data.get("ocr_data")

            # 3️⃣ Validate
            data, context = await execute_step(validate_document, data, context, "04_VALIDATE")
            result["validation"] = data.get("validation_status")

            # 4️⃣ ERP post
            if result["validation"] == "VALID":
                erp_payload, context = await execute_step(post_to_erp, data, context, "06_ERP_POST")
                result["erp_id"] = erp_payload.get("erp_id")

            result["status"] = "COMPLETED"

        except Exception as e:
            result["errors"].append(str(e))

        return {
            "doc_type": result["doc_type"],
            "document_validation_status": result["validation"],
            "ocr_data": result["ocr_data"],
            "erp_id": result.get("erp_id"),
            "summary": {
                "document_type": result["doc_type"],
                "document_validation_status": result["validation"],
                "confidence": result.get("confidence", 0),
                "key_fields": result.get("ocr_data", {}).get("extracted_fields", {}) if result.get("ocr_data") else {},
            }
        }
    
# -----------------------------
# Parent Workflow
# -----------------------------
@workflow.defn
class CustomerOnboardingWorkflow:
    @workflow.run
    async def run(self, payload: Dict[str, Any]):
        """Main onboarding workflow"""

        wf_id = workflow.info().workflow_id
        context = build_base_context(payload, wf_id)
        print(f"🚀 Starting workflow: {wf_id} with input \n {payload}")

        # Step 1: preprocess
        pre_payload, context = await execute_step(pre_process_documents, payload, context, "01_PREPROCESS")
        docs = pre_payload.get("normalized_documents", [])

        # Step 2: fan-out child workflows
        child_handles = []
        for i, doc in enumerate(docs):
            child_id = f"{wf_id}_{doc.get('declared_doc_type')}_{i}"  # unique child id

            child_context = merge_context(
                context,
                {
                    "doc_type": doc.get("declared_doc_type"),
                    "item_id": doc.get("item_id"),
                    "child_workflow_id": child_id,
                    "parent_workflow_id": wf_id,
                    "branch_id": f"DOC_{i}",
                    "execution_path_id": f"{wf_id}:DOC_{i}",
                    "fanout_group_id": f"{wf_id}:01_PREPROCESS",
                },
            )
            handle = workflow.execute_child_workflow(
                DocumentWorkflow.run,
                {"data": doc, "context": child_context},
                id=child_id,
                task_queue=TASK_QUEUE,
                execution_timeout=timedelta(minutes=5),
            )
            child_handles.append(handle)

        # Aggregate result in parent workflow
        results = [await h for h in child_handles]  # collect results
        aggregated_summary = {
            "passport": None,
            "driving_licence": None,
            "utility_bill": None,
        }

        for r in results:
            doc_type = r.get("doc_type")

            if doc_type:
                key = doc_type.lower().replace(" ", "_")
                aggregated_summary[key] = r

        # Step 3: cross verification
        cross_payload, context = await execute_step(
            cross_document_verification, {"documents": results}, context, "05_CROSS_VERIFY"
        )

        final_decision = cross_payload.get("decision")

        # Step 4: log approval decision
        cross_payload, context = await execute_step(
            approval_decision,
            {"documents": cross_payload.get("documents"), "decision": cross_payload.get("decision"), "missing_documents": cross_payload.get("missing_documents")},
            context,
            "08_APPROVAL_DECISION",
        )

        # Step 5: audit
        await execute_step(
            store_audit,
            {
                "workflow_id": wf_id,
                "documents": results,
                "decision": final_decision,
            },
            context,
            "07_AUDIT",
        )

        # Step 6: mark workflow completed
        upsert_workflow_instance(
            workflow_id=wf_id,
            workflow_type=payload.get("workflow_type"),
            status="COMPLETED",
            input_data=payload,
            header_id=payload.get("header_id"),
            reference_id=payload.get("reference_id"),
        )

        erp_ids = [r.get("erp_id") for r in results if r.get("erp_id")]
        return {"status": "COMPLETED", "decision": final_decision, "erp_ids": erp_ids}

# -----------------------------
# Worker
# -----------------------------
async def main():
    print("\n🚀 STARTING TEMPORAL KYC WORKER")
    print(f"Connecting to: {TEMPORAL_HOST}\n")

    client = await Client.connect(TEMPORAL_HOST)

    print("✅ Connected to Temporal\n")

    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[CustomerOnboardingWorkflow, DocumentWorkflow],
        activities=[
            pre_process_documents,
            ai_classify_document,
            ai_process_doc,
            validate_document,
            cross_document_verification,
            approval_decision,
            post_to_erp,
            store_audit,
        ],
    )

    async with worker:
        print("🚀 Worker running...")
        await asyncio.Event().wait()

# Entry point
if __name__ == "__main__":
    asyncio.run(main())