from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import os
import json
from azure.core.credentials import AzureKeyCredential
from azure.ai.formrecognizer import DocumentAnalysisClient
from openai import OpenAI

# Import DB abstraction layer
import wf_ai_fastapi.routers.process_db as db

# ---------------------------
# Environment Validation
# ---------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY not set")

router = APIRouter(prefix="/ai_bpm", tags=["AI Lifecycle"])

# ---------------------------
# Clients
# ---------------------------
class AIClients:
    _llm_client = None

    @classmethod
    def llm(cls):
        if cls._llm_client is None:
            cls._llm_client = OpenAI(
                api_key=os.getenv("OPENAI_API_KEY")
            )
        return cls._llm_client

# =========================================================
# REQUEST / RESPONSE MODELS
# =========================================================
class AIRequest(BaseModel):
    action: str
    context: Dict[str, Any] = Field(default_factory=dict)
    options: Optional[Dict[str, Any]] = Field(default_factory=dict)


class AIResponse(BaseModel):
    action: str
    transaction: str
    result: Dict[str, Any]
    confidence: Optional[float] = None


# =========================================================
# DB SIGNAL FETCHERS
# =========================================================

def get_latest_workflow(header_id: int):
    rows = db.run_query("""
        SELECT workflow_id, workflow_type, status,
               current_step, decision
        FROM workflow_instance
        WHERE header_id = %s
        ORDER BY created_at DESC
        LIMIT 1
    """, (header_id,))
    return rows[0] if rows else None


def get_latest_activity(workflow_id: str):
    rows = db.run_query("""
        SELECT step_key, task_name, status
        FROM workflow_activity_instance
        WHERE workflow_id = %s
        ORDER BY start_time DESC
        LIMIT 1
    """, (workflow_id,))
    return rows[0] if rows else None


def get_latest_approval(header_id: int):
    rows = db.run_query("""
        SELECT task_name, status, decision, assigned_to
        FROM workflow_approval_task
        WHERE header_id = %s
        ORDER BY created_at DESC
        LIMIT 1
    """, (header_id,))
    return rows[0] if rows else None


def get_latest_erp(header_id: int):
    rows = db.run_query("""
        SELECT doc_id, approval_status
        FROM erp_crm_documents
        WHERE header_id = %s
        ORDER BY created_at DESC
        LIMIT 1
    """, (header_id,))
    return rows[0] if rows else None


def get_header(header_id: int):
    h = db.get_process_header(header_id)
    return {
        "reference_id": h["reference_id"],
        "workflow_type": h["workflow_type"],
        "process_name": h["process_name"]
    }


def extract_business_signal(header_id: int):
    rows = db.run_query("""
        SELECT extracted_fields
        FROM workflow_ocr_data
        WHERE header_id = %s
        ORDER BY version DESC
        LIMIT 1
    """, (header_id,))

    if not rows:
        return {}

    header = rows[0]["extracted_fields"].get("header", {})

    return {
        "vendor": header.get("VendorName"),
        "amount": header.get("InvoiceTotal"),
        "invoice_number": header.get("InvoiceId"),
        "invoice_date": header.get("InvoiceDate")
    }


# =========================================================
# SNAPSHOT BUILDER
# =========================================================

def build_snapshot(header_id: int):

    header = get_header(header_id)
    workflow = get_latest_workflow(header_id)

    activity = get_latest_activity(workflow["workflow_id"]) if workflow else None
    approval = get_latest_approval(header_id)
    erp = get_latest_erp(header_id)
    business = extract_business_signal(header_id)

    return {
        "transaction": header["reference_id"],
        "workflow_type": header["workflow_type"],
        "process_name": header["process_name"],
        "business": business,
        "state": {
            "workflow": workflow,
            "activity": activity,
            "approval": approval,
            "erp": erp
        }
    }


# =========================================================
# SYSTEM PROMPT (STRICT ENGINE)
# =========================================================
# =========================================================
# 🔥 LLM PROMPT (STRICT, NO FLUFF)
# =========================================================
SYSTEM_PROMPT = """
You are a business transaction status engine.

You must produce BOTH:
1. Structured JSON (for system use)
2. Human-readable summary (for business user)

STRICT RULES:
- Always include transaction id
- Always include key business fields (vendor, amount if available)
- Never invent data
- Never output generic explanations
- Human output must be structured, concise, and scannable

OUTPUT MUST BE VALID JSON ONLY.

OUTPUT FORMAT:

{
  "structured": {
    "transaction": "...",
    "lifecycle_position": "...",   // STEP (STATUS, DECISION if exists)
    "path": "...",
    "status_map": {},              // MUST be object, not string
    "completed_steps": [],
    "blocking_step": null,
    "waiting_for": null,
    "next_action": "...",
    "confidence_note": "..."
  },
  "human_readable": "MULTI-LINE TEXT"
}
"""

def build_prompt(snapshot: Dict[str, Any]):

    return f"""
ACTION: where_in_lifecycle

INPUT SNAPSHOT:
{json.dumps(snapshot, indent=2)}

INSTRUCTIONS:

1. Determine lifecycle position:
   Combine step + status + decision
   Example: ERP_POST (COMPLETED, MANUAL_APPROVED)

2. Build execution path:
   Invoice: PREPROCESS → OCR → NORMALIZE → VALIDATE → APPROVAL → ERP_POST  
   KYC: PREPROCESS → OCR → VALIDATE → APPROVAL → ERP

3. Build status_map:
   ✓ = completed
   ⏳ = in progress
   ⬜ = not started

4. completed_steps (ONLY if evidence exists):
   - OCR → OCR_COMPLETE
   - validation passed → VALIDATION_PASSED
   - approval decision → APPROVED
   - ERP exists → ERP_POSTED

5. blocking logic:
   - approval pending → DOCUMENT_APPROVAL
   - validation failure → VALIDATE
   - else null

6. waiting_for:
   - manual approval → assigned_to
   - else null

7. next_action: (provide one of the following based on lifecycle position completed_steps and blocking logic)
   - start workflow if not started → "Start workflow"
   - approval pending → "Review approval queue"
   - completed → "No action required"
   - failed → "Fix validation issue"

8. confidence_note:
   MUST reference real signals (approval, ERP, validation)

9. HUMAN Readable Business Summary GUIDELINES:
Include following with less than 3 sentences only with following key insights:
- Lifecycle Status with key data points (transaction + vendor + amount + position etc.)
- Completed Steps (only evidence-backed)
- Current Status (blocking or completed)

STYLE:
- Business tone writing communicating key insights to a business user
- No JSON-like formatting

Keep concise. No paragraphs. No fluff.
"""

# =========================================================
# LLM CALL
# =========================================================

def run_llm(prompt: str, model: str = "gpt-4o-mini"):

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    response = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )

    raw = response.choices[0].message.content

    try:
        return json.loads(raw)
    except:
        return {
            "error": "invalid_json",
            "raw": raw
        }


# =========================================================
# MAIN ROUTER
# =========================================================
@router.post("/ai-reasoning", response_model=AIResponse)
async def ai_reasoning(req: AIRequest):
    """Endpoint for AI reasoning on documents with action-aware context building and unified prompt transformation.
            where_in_lifecycle, is_everything_correct, needs_attention, root_cause, what_next
    ```json
    {
        "action": "where_in_lifecycle",
        "context": {
            "workflowId": "INV-20260414-B125B3-202604141803",
            "headerId": 34,
            "referenceId": "INV-20260414-B125B3"
            }
    }
    ```
    """
    try:
        header_id = req.context.get("headerId")

        if not header_id:
            raise HTTPException(status_code=400, detail="headerId is required")

        # 1. Build deterministic snapshot
        snapshot = build_snapshot(header_id)

        # 2. Build prompt
        prompt = build_prompt(snapshot)

        # 3. Call LLM
        model = req.options.get("model", "gpt-4o-mini") if req.options else "gpt-4o-mini"
        result = run_llm(prompt, model)

        # 4. Extract confidence safely
        confidence = None
        if isinstance(result, dict):
            confidence = result.get("structured", {}).get("confidence")

        return AIResponse(
            action=req.action,
            transaction=snapshot["transaction"],
            result=result,
            confidence=confidence
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))