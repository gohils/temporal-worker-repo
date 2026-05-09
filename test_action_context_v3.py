import json
import os
from typing import Dict, Any, Optional
from openai import OpenAI
import wf_ai_fastapi.routers.process_db as db

# AI Decision Layer for Human Workflow Acceleration (Manager Copilot for Approvals)


# =========================================================
# 🧠 DB LAYER (UNCHANGED - SOURCE OF TRUTH)
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
# 🧠 APPROVAL-CENTRIC SNAPSHOT (NEW)
# =========================================================

def build_approval_snapshot(header_id: int):

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

        "approval_context": {
            "workflow_status": workflow,
            "current_activity": activity,
            "approval_task": approval,
            "erp_state": erp
        }
    }


# =========================================================
# 🧠 SYSTEM PROMPT (DECISION ENGINE - NOT REPORTER)
# =========================================================

SYSTEM_PROMPT = """
You are an AI Approval Decision Assistant for managers.

Your job is NOT to describe workflows.

Your job IS to help managers approve faster with high confidence.
You do NOT calculate risk.
You do NOT create uncertainty.
You do NOT evaluate probability.

You ONLY explain why the system state is safe or requires action.

You must produce VALID JSON ONLY.

business_summary RULE (MANDATORY):

You MUST generate the summary business_summary using this exact structure:

"Invoice {transaction} from {vendor} ({amount}) {lifecycle_result} including {key_stages}. {final_action_state}."

RULES:
- Do NOT change sentence structure
- Only fill placeholders
- Use factual workflow states only
- Keep it single sentence

OUTPUT FORMAT:

{
  "approval_brief": {
    "transaction": "...",
    "vendor": "...",
    "amount": "...",

    "business_summary": "2-3 line executive summary",

    "facts": [
      "Only verified system facts (ERP posted, validation passed, approval completed)"
    ],

    "blocking_reason": "null or exact system reason (if any)",

    "next_required_action": "Approve | Wait for system step | None",

    "system_state": {
      "approval_status": "...",
      "erp_status": "...",
      "workflow_status": "..."
    }
  }
}

PRE-CONDITION RULE (MANDATORY):

IF ANY OF THE FOLLOWING IS TRUE:
- approval_context.workflow_status is null
- approval_context.approval_task is null

THEN:

You MUST NOT generate invoice-style business_summary.

Instead, you MUST return:

"Transaction {transaction} is not in an approval-ready state. Workflow processing has not started or no approval task is available."

RULES:
- Do NOT mention vendor or amount
- Do NOT use invoice wording
- Do NOT output null values
- Do NOT attempt lifecycle explanation

RULES:
- Do NOT invent missing data
- Do NOT describe full lifecycle
- Focus ONLY on approval decision support
- Only factual interpretation of system state
- Be concise, executive-level
"""


# =========================================================
# 🧠 PROMPT BUILDER (MINIMAL + DECISION FOCUSED)
# =========================================================
def build_prompt(snapshot: Dict[str, Any]):

    return f"""
APPROVAL FACT REVIEW TASK

INPUT APPROVAL FACTS:
{json.dumps(snapshot, indent=2)}

TASK:
Convert system approval facts into a clear manager-ready approval brief.

RULES:
- Use ONLY provided facts
- Do NOT infer missing information
- Do NOT describe workflow steps
- Focus ONLY on approval readiness
- Output must be directly usable for manager decision screen
"""


# =========================================================
# 🧠 LLM EXECUTION
# =========================================================

def run_llm(prompt: str):

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

    headers = [31,34]

    for header_id in headers:

        snapshot = build_approval_snapshot(header_id)

        print("\n===== SNAPSHOT =====\n")
        print(json.dumps(snapshot, indent=2))

        prompt = build_prompt(snapshot)

        print("\n===== AI APPROVAL BRIEF =====\n")
        result = run_llm(prompt)

        print(json.dumps(result, indent=2))