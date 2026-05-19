# -----------------------------
# loan_document_intelligence_worker.py
# -----------------------------

import asyncio, json, uuid, os
from dataclasses import dataclass
from datetime import timedelta
from typing import Dict, Any
import re

from temporalio import workflow, activity
from temporalio.client import Client
from temporalio.worker import Worker
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    import httpx
    from ai_worker_db_log import (
        log_activity,
        upsert_workflow_instance,
        get_items_details,
        store_document_artifact
    )

# =========================================================
# CONFIG
# =========================================================
TEMPORAL_HOST = os.getenv("TEMPORAL_HOST", "localhost:7233")
TASK_QUEUE = os.getenv("TASK_QUEUE", "loan-document-queue")
AI_API_URL = os.getenv("AI_API_URL", "http://localhost:8000")

# =========================================================
# CONTRACTS
# =========================================================
@dataclass
class ActivityInput:
    payload: Dict[str, Any]
    context: Dict[str, Any]

@dataclass
class ActivityOutput:
    response: Dict[str, Any]
    context: Dict[str, Any]

SCHEMAS = {
    "driver_license": {
        "required_fields": [
            "name",
            "license_number",
            "address",
            "expiry_date",
            "date_of_birth"
        ]
    },
    "passport": {
        "required_fields": [
            "passport_number",
            "name",
            "nationality",
            "expiry_date"
        ]
    },
    "bank_statement": {
        "required_fields": [
            "account_number",
            "bank_name",
            "balance"
        ]
    },
    "payslip": {
        "required_fields": [
            "employee_name",
            "salary",
            "pay_period"
        ]
    },
    "default": {
        "required_fields": [
            "name"
        ]
    }
}

# =========================================================
# CONTEXT HELPERS (IDENTICAL TO INVOICE)
# =========================================================
def build_base_context(payload, wf_id):
    params = payload.get("input_parameters", {})
    return {
        "workflow_id": wf_id,
        "workflow_type": payload.get("workflow_type"),
        "reference_id": payload.get("reference_id"),
        "header_id": params.get("header_id"),
        "item_id": params.get("item_id"),
    }

def merge_context(parent, child):
    return {
        **parent,
        **child,
        "workflow_id": parent.get("workflow_id"),
        "workflow_type": parent.get("workflow_type"),
        "reference_id": parent.get("reference_id"),
        "header_id": child.get("header_id") or parent.get("header_id"),
        "item_id": child.get("item_id") or parent.get("item_id"),
        "document_url": child.get("document_url") or parent.get("document_url"),
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
# 01 PREPROCESS (NORMALIZE SINGLE DOCUMENT)
# =========================================================
@activity.defn
@log_activity(display_name="01_PREPROCESS")
async def preprocess(input: ActivityInput) -> ActivityOutput:

    header_id = input.payload.get("input_parameters", {}).get("header_id")
    item_id = input.payload.get("input_parameters", {}).get("item_id")

    if not header_id or not item_id:
        raise ValueError("Missing header_id or item_id")

    # fetch document from DB
    doc = get_items_details(header_id, item_id)

    if not doc:
        raise ValueError("Document not found")

    normalized = {
        "item_id": str(item_id),
        "header_id": str(header_id),
        "document_url": doc["document_url"],
        "doc_type_hint": doc.get("doc_type", "UNKNOWN")
    }

    return ActivityOutput(
        {"document": normalized},
        {"item_id": str(item_id), "header_id": str(header_id)}
    )

# =========================================================
# 02 OCR (GENERIC CLOUD AGNOSTIC)
# =========================================================
@activity.defn
@log_activity(display_name="02_OCR")
async def ocr(input: ActivityInput) -> ActivityOutput:

    doc = input.payload.get("document", {})
    doc_url = doc.get("document_url")

    if not doc_url:
        raise ValueError("Missing document_url")

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{AI_API_URL}/ai_doc/analyze-document-prebuilt-model",
            json={
                "ai_model_name": "prebuilt-read",
                "document_url": doc_url,
                "response_format": "plain_text"
            },
        )
        resp.raise_for_status()
        ocr_data = resp.json()

    raw_text = ocr_data.get("documents", "")

    print(f"=============== OCR Result: {ocr_data}")
    doc_id = store_document_artifact(
        workflow_id=input.context["workflow_id"],
        document_url=doc_url,
        header_id=input.context.get("header_id"),
        item_id=input.context.get("item_id"),
        doc_type=input.context.get("doc_type", "UNKNOWN"),
        ocr_raw=json.dumps(ocr_data),
        ocr_result=ocr_data,
        status="OCR_COMPLETE"
    )
    return ActivityOutput(
        {"document_id": doc_id, "raw_text": raw_text, "ocr_data": ocr_data},  # return OCR data
        {"document_id": doc_id},          # update context
    )


# =========================================================
# 03 LLM CLASSIFY
# =========================================================
@activity.defn
@log_activity(display_name="03a_LLM_CLASSIFY")
async def llm_classify(input: ActivityInput) -> ActivityOutput:

    raw_text = input.payload.get("raw_text")
    if not raw_text:
        raise ValueError("Missing raw_text from OCR step")

    prompt = f"""
You are a STRICT document classification engine.

Classify OCR text into exactly ONE type:

- driver_license
- passport
- bank_statement
- payslip
- unknown

RULES:
- Output ONLY valid JSON
- No explanation
- No extra keys

FORMAT:
{{
  "document_type": "driver_license"
}}

OCR TEXT:
{raw_text}
"""

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{AI_API_URL}/ai_doc_llm/execute_llm",
            json={"prompt": prompt, "context": {}},
        )
        resp.raise_for_status()
        llm_result = resp.json()

    raw_output = llm_result.get("result", {}).get("response", "{}")

    # ---------------- SAFE JSON PARSE ----------------
    try:
        parsed = json.loads(raw_output)
    except Exception:
        # fallback: regex extraction (LLM sometimes wraps text)
        match = re.search(r'"document_type"\s*:\s*"([^"]+)"', raw_output)
        parsed = {
            "document_type": match.group(1) if match else "unknown"
        }

    doc_type = parsed.get("document_type", "unknown").strip().lower()

    return ActivityOutput(
        {"doc_type": doc_type},
        {"doc_type": doc_type}
    )

# =========================================================
# 03 LLM PROCESSING
# =========================================================
@activity.defn
@log_activity(display_name="03b_LLM_EXTRACT")
async def llm_process(input: ActivityInput) -> ActivityOutput:

    raw_text = input.payload.get("raw_text")
    doc_type = input.payload.get("doc_type") or input.context.get("doc_type", "default")

    if not raw_text:
        raise ValueError("Missing raw_text from OCR step")

    schema = SCHEMAS.get(doc_type, SCHEMAS["default"])
    required_fields = schema["required_fields"]

    prompt = f"""
You are a HIGH-PRECISION document extraction engine.

You must extract structured data from OCR text.

========================
DOCUMENT TYPE
========================
{doc_type}

========================
REQUIRED FIELDS
========================
{json.dumps(required_fields, indent=2)}

========================
CRITICAL RULES
========================
1. Output ONLY valid JSON
2. You MUST include ALL required fields
3. If a field is not found in OCR text, set it to null
4. DO NOT hallucinate or guess values
5. DO NOT add extra fields
6. JSON must be valid and parseable

========================
OUTPUT FORMAT
========================
Return exactly:
{{
  "field1": "...",
  "field2": null
}}

========================
OCR TEXT
========================
{raw_text}
"""

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{AI_API_URL}/ai_doc_llm/execute_llm",
            json={"prompt": prompt, "context": {}},
        )
        resp.raise_for_status()
        llm_result = resp.json()

    raw_output = llm_result.get("result", {}).get("response", "{}")

    # ---------------- SAFE JSON PARSE ----------------
    try:
        extracted = json.loads(raw_output)
    except Exception:
        # last-resort fallback
        extracted = {
            "parse_error": True,
            "raw_llm_output": raw_output
        }

    # ---------------- VALIDATION ENFORCEMENT ----------------
    # Ensure all required fields exist (fixes missing field problem)
    normalized = {}
    for field in required_fields:
        normalized[field] = extracted.get(field, None)

    return ActivityOutput(
        {
            "structured_text": normalized,
            "llm_output": normalized
        },
        {}
    )

# =========================================================
# 04 store_results UPDATE (SINGLE DOCUMENT STATE UPDATE)
# =========================================================
@activity.defn
@log_activity(display_name="04_STORE_RESULTS")
async def store_results(input: ActivityInput) -> ActivityOutput:

    print("=== DOCUMENT Result UPDATE ===")
    print(json.dumps(input.payload, indent=2))

    final_id = f"ai_doc-{uuid.uuid4().hex[:8]}"

    store_document_artifact(
        workflow_id=input.context["workflow_id"],
    document_url=input.context.get("document_url"),
        header_id=input.context.get("header_id"),
        item_id=input.context.get("item_id"),
        extracted_fields={
    "doc_type": input.payload.get("doc_type"),
    "structured": input.payload.get("structured_text"),
},
        status="COMPLETED"
    )

    return ActivityOutput(
        {**input.payload, "document_id": final_id},
        {"result": {"id": final_id}}
    )

# =========================================================
# 05 AUDIT
# =========================================================
@activity.defn
@log_activity(display_name="05_AUDIT")
async def audit(input: ActivityInput) -> ActivityOutput:

    print("=== AUDIT LOG ===")
    print(json.dumps(input.payload, indent=2))

    return ActivityOutput({"audit": "done"}, {})

# =========================================================
# WORKFLOW
# =========================================================
# {
#   "workflow_type": "AIDocumentWorkflow",
#   "workflow_prefix": "LOAN_DOC",
#   "input_parameters": {
#     "document_url": "https://zblobarchive.blob.core.windows.net/samples/aus_dl_sample1.JPG"
#   },
#   "task_queue": "loan-document-queue"
# }
@workflow.defn
class AIDocumentWorkflow:

    @workflow.run
    async def run(self, req: Dict):

        print("workflow input payload ======",req)
        wf_id = workflow.info().workflow_id
        payload = req
        context = build_base_context(payload, wf_id)

        # STEP 1
        payload, context = await execute_step(preprocess, payload, context, "PREPROCESS")

        # STEP 2
        payload, context = await execute_step(ocr, payload, context, "OCR")

        # STEP 3
        payload, context = await execute_step(llm_classify, payload, context, "LLM_CLASSIFY")
        # STEP 3
        payload, context = await execute_step(llm_process, payload, context, "LLM_PROCESS")

        # STEP 4
        payload, context = await execute_step(store_results, payload, context, "STORE_RESULTS")

        # STEP 5
        await execute_step(audit, payload, context, "AUDIT")

        return {
            "status": "COMPLETED",
            "workflow_id": wf_id,
            "document_url": context.get("document_url")
        }

# =========================================================
# WORKER
# =========================================================
async def main():

    client = await Client.connect(TEMPORAL_HOST)

    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[AIDocumentWorkflow],
        activities=[preprocess, ocr, llm_classify, llm_process, store_results, audit],
    )

    async with worker:
        print("🚀 AI Document Worker Running (Unified Artifact Model)")
        await asyncio.Event().wait() 


if __name__ == "__main__":
    asyncio.run(main())