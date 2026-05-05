import json
from typing import Dict, Any, Optional
import wf_ai_fastapi.routers.process_db as db


# =========================================================
# 🔥 DATA EXTRACTION (UNCHANGED - CLEAN SIGNAL)
# =========================================================

def get_latest_workflow(header_id: int) -> Optional[Dict[str, Any]]:
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


# =========================================================
# 🔥 SNAPSHOT (MINIMAL SIGNAL ONLY)
# =========================================================
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

    ocr = rows[0]["extracted_fields"]
    header = ocr.get("header", {})

    return {
        "vendor": header.get("VendorName"),
        "amount": header.get("InvoiceTotal"),
        "invoice_number": header.get("InvoiceId"),
        "invoice_date": header.get("InvoiceDate")
    }

def build_snapshot(header_id: int):

    header = get_header(header_id)
    workflow = get_latest_workflow(header_id)

    activity = None
    if workflow:
        activity = get_latest_activity(workflow["workflow_id"])

    approval = get_latest_approval(header_id)
    erp = get_latest_erp(header_id)

    business = extract_business_signal(header_id)

    return {
        "transaction": header["reference_id"],
        "workflow_type": header["workflow_type"],
        "process_name": header["process_name"],

        # 🔥 ADD THIS
        "business": business,

        "state": {
            "workflow": workflow,
            "activity": activity,
            "approval": approval,
            "erp": erp
        }
    }

# =========================================================
# 🔥 LLM PROMPT (STRICT, NO FLUFF)
# =========================================================
# =========================================================
# SYSTEM PROMPT (STRICT ENGINE)
# =========================================================
# =========================================================
# 🔥 LLM PROMPT (STRICT, NO FLUFF)
# =========================================================
SYSTEM_PROMPT = """
You are a business report formatter.

RULES:
- Do not change input data
- Do not infer missing fields
- Output ONLY valid JSON

OUTPUT FORMAT:
{
  "structured": object (unchanged input),
  "human_readable": string (exactly 2 sentences)
}

HUMAN_READABLE RULE (STRICT):

Sentence 1 MUST be exactly:
"The invoice transaction {transaction} from vendor {vendor} for the amount of {amount} has been {status}."

Where:
- status = workflow.state.workflow.status

Sentence 2:
One sentence describing lifecycle state and next action using only provided fields.

NO deviations allowed.
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

7. next_action:
   - approval pending → "Review approval queue"
   - completed → "No action required"
   - failed → "Fix validation issue"

8. confidence_note:
   MUST reference real signals (approval, ERP, validation)

9. HUMAN Readable Business Summary GUIDELINES:
Include following with Exactly 2 sentences only with following key insights:
- Lifecycle Status with key data points (transaction + vendor + amount + position etc.)
- Completed Steps (only evidence-backed)
- Current Status (blocking or completed)

FORMAT RULE:
- Exactly 2 sentences only

Sentence 1:
Describe current lifecycle state in plain business language.

Sentence 2:
Describe what is happening next (or completion status).

STYLE:
- Business executive tone
- No JSON-like formatting

Keep concise. No paragraphs. No fluff.
"""

# =========================================================
# 🔥 LLM EXECUTION
# =========================================================

def run_llm(prompt: str):

    import os
    from openai import OpenAI

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    response = client.chat.completions.create(
        model="gpt-4o-mini",
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
        return {"error": "invalid_json", "raw": raw}


# =========================================================
# 🚀 ENTRY POINT
# =========================================================

if __name__ == "__main__":

    # testing single action for faster iteration
    headers = [31, 34]
    for header_id in headers:

        snapshot = build_snapshot(header_id)

        print(f"\n================ SNAPSHOT header_id ===== {header_id} ============\n")
        print(json.dumps(snapshot, indent=2))

        # prompt = build_prompt(snapshot)

        print(f"\n================ LLM OUTPUT header_id ===== {header_id} ============\n")
        result = run_llm(json.dumps(snapshot, indent=2))

        print(f"\n================ LLM OUTPUT header_id ===== {header_id} ============\n")
        print(result)