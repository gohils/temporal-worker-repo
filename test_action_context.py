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

def build_snapshot(header_id: int):

    header = get_header(header_id)
    workflow = get_latest_workflow(header_id)

    activity = None
    if workflow:
        activity = get_latest_activity(workflow["workflow_id"])

    approval = get_latest_approval(header_id)
    erp = get_latest_erp(header_id)

    return {
        "transaction": header["reference_id"],
        "workflow_type": header["workflow_type"],
        "process_name": header["process_name"],
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

SYSTEM_PROMPT = """
You are a business transaction status engine.

Your job is NOT to explain workflows.
Your job is NOT to describe systems.

Your job is to OUTPUT structured lifecycle status for a business user.

STRICT RULES:
- Always anchor response using transaction id
- Use ONLY given data (no assumptions)
- Show evidence of completed steps
- Never produce generic explanations
- Never describe workflow in paragraphs

OUTPUT FORMAT (JSON ONLY):

{
  "transaction": "...",

  "lifecycle_position": "...",

  "path": "...",

  "status_map": "...",

  "completed_steps": [],

  "blocking_step": "...",

  "waiting_for": "...",

  "next_action": "...",

  "confidence_note": "..."
}
"""


def build_user_prompt(snapshot: Dict[str, Any]):

    return f"""
ACTION: where_in_lifecycle

INPUT SNAPSHOT:
{json.dumps(snapshot, indent=2)}

INSTRUCTIONS:

1. Identify CURRENT lifecycle step using:
   - workflow.status
   - last activity.step_key
   - approval status
   - erp status

2. Build execution path:
   Invoice: PREPROCESS → OCR → NORMALIZE → VALIDATE → APPROVAL → ERP_POST  
   KYC: PREPROCESS → OCR → VALIDATE → APPROVAL → ERP

3. Build status_map using:
   ✓ = completed
   ⏳ = in progress / waiting
   ⬜ = not started

4. completed_steps MUST be backed by data:
   - OCR exists → OCR_COMPLETE
   - validation step passed → VALIDATION_PASSED
   - approval decision exists → APPROVED
   - erp exists → ERP_POSTED

5. blocking_step:
   - approval pending → DOCUMENT_APPROVAL
   - validation failure → VALIDATE
   - else null

6. waiting_for:
   - if manual approval → approver
   - else null

7. next_action:
   - approval pending → "Review approval queue"
   - completed → "No action required"
   - failed → "Fix validation issue"

8. confidence_note:
   MUST explain why earlier steps are safe (based on evidence)

Return ONLY JSON.
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

    header_id = 34  # test case

    snapshot = build_snapshot(header_id)

    print("\n================ SNAPSHOT =================\n")
    print(json.dumps(snapshot, indent=2))

    prompt = build_user_prompt(snapshot)

    print("\n================ LLM OUTPUT =================\n")
    result = run_llm(prompt)

    print(json.dumps(result, indent=2))