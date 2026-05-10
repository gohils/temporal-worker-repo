import json
from typing import List, Dict, Any
from openai import OpenAI
import wf_ai_fastapi.routers.process_db as db


# =========================================================
# 🧠 SOURCE OF TRUTH WORKFLOW
# =========================================================
WORKFLOW_STEPS = [
    "01_PREPROCESS",
    "02_OCR",
    "03_NORMALIZE",
    "04_VALIDATE",
    "05_3WAY_MATCHING",
    "06_DECISION",
    "07_ERP",
    "08_AUDIT"
]


# =========================================================
# 🧠 SERIALIZER
# =========================================================
def json_serializer(obj):
    from datetime import datetime, date
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return str(obj)


# =========================================================
# 🧠 DB FETCH (MINIMAL)
# =========================================================
def get_header(header_id: int):
    h = db.get_process_header(header_id)
    return {
        "transaction_id": h["reference_id"],
        "vendor": h["declared_data"].get("vendor_name"),
        "amount": h["declared_data"].get("amount"),
    }


def get_latest_workflow(header_id: int):
    rows = db.run_query("""
        SELECT workflow_id, status
        FROM workflow_instance
        WHERE header_id = %s
        ORDER BY created_at DESC
        LIMIT 1
    """, (header_id,))
    return rows[0] if rows else None


def get_latest_activity(workflow_id: str):
    rows = db.run_query("""
        SELECT step_key, status
        FROM workflow_activity_instance
        WHERE workflow_id = %s
        ORDER BY start_time ASC
    """, (workflow_id,))
    return rows if rows else []


# =========================================================
# 🧠 BUILD LIFECYCLE (PURE DETERMINISTIC ENGINE)
# =========================================================
def build_lifecycle(activity_rows: List[Dict[str, Any]]):
    status_map = {a["step_key"]: a["status"] for a in activity_rows}

    lifecycle = []
    completed = []
    pending = []
    failed = None
    current = None

    for step in WORKFLOW_STEPS:
        status = status_map.get(step, "PENDING")

        lifecycle.append({
            "step": step,
            "status": status
        })

        if status == "COMPLETED":
            completed.append(step)

        elif status == "FAILED":
            failed = step
            current = step

        elif current is None:
            current = step

        if status in ["PENDING", "FAILED"]:
            pending.append(step)

    overall_state = (
        "FAILED" if failed else
        "SUCCESS" if len(completed) == len(WORKFLOW_STEPS) else
        "IN_PROGRESS"
    )

    return lifecycle, completed, pending, current, failed, overall_state


# =========================================================
# 🧠 CONTEXT BUILDER (LIFECYCLE ONLY)
# =========================================================
def build_context(header_id: int):

    header = get_header(header_id)
    workflow = get_latest_workflow(header_id)

    activity = get_latest_activity(workflow["workflow_id"]) if workflow else []

    lifecycle, completed, pending, current, failed, overall_state = build_lifecycle(activity)

    return {
        "transaction_id": header["transaction_id"],
        "vendor": header["vendor"],
        "amount": header["amount"],

        "lifecycle_view": lifecycle,

        "execution_state": {
            "completed_steps": completed,
            "pending_steps": pending,
            "current_step": current,
            "failed_step": failed
        },

        "workflow_snapshot": {
            "workflow_id": workflow["workflow_id"] if workflow else None,
            "workflow_status": workflow["status"] if workflow else None,
            "overall_state": overall_state
        }
    }


# =========================================================
# 🧠 OPTIONAL LLM FORMATTER (NO LOGIC)
# =========================================================
LIFECYCLE_PROMPT = """
You are a Workflow Intelligence Engine for enterprise operations (SAP / Salesforce grade).

Your job is NOT to explain.
Your job is NOT to reason.
Your job is NOT to summarize.

Your job is to produce an OPERATIONAL INTELLIGENCE CARD that allows a business user to understand:
- What happened
- Where the transaction is
- Whether action is required
- What is blocking it
- What is completed vs pending

This output must be consumable WITHOUT opening any other system.

INPUT:
{input}

OUTPUT JSON ONLY:

{
  "transaction": {
    "transaction_id": "",
    "vendor": "",
    "amount": ""
  },

  "operational_status": {
    "state": "SUCCESS | IN_PROGRESS | FAILED",
    "current_step": "",
    "health": "GREEN | AMBER | RED"
  },

  "lifecycle_view": [
    {
      "step": "",
      "status": ""
    }
  ],

  "execution_summary": {
    "completed_steps": [],
    "pending_steps": [],
    "failed_step": null,
    "next_action_step": ""
  },

  "workflow_snapshot": {
    "workflow_id": "",
    "workflow_status": "",
    "overall_state": ""
  },

  "decision_snapshot": {
    "approval_status": "",
    "decision": "",
    "erp_status": ""
  },

  "action_intelligence": {
    "action_required": "YES | NO",
    "priority": "LOW | MEDIUM | HIGH | CRITICAL",
    "reason": ""
  },

  "human_readable_card": {
    "headline": "",
    "summary": "",
    "status_line": "",
    "action_line": ""
  }
}

ALWAYS add a HUMAN SUMMARY at the end:

- Do NOT change workflow order
- Do NOT infer missing steps
- Do NOT hallucinate causes
- Do NOT add external information

Statuses allowed:
- COMPLETED
- CURRENT
- PENDING
- FAILED

Current step = first non-COMPLETED step OR explicitly marked CURRENT/FAILED

Failure only exists if explicitly present in input

"""


def run_llm(prompt: str):
    client = OpenAI()

    res = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    return res.choices[0].message.content


# =========================================================
# 🚀 MAIN
# =========================================================
def process(header_id: int):

    context = build_context(header_id)

    print("\n================ LIFECYCLE CONTEXT ================\n")
    print(json.dumps(context, indent=2, default=json_serializer))

    prompt = LIFECYCLE_PROMPT.replace(
        "{input}",
        json.dumps(context, indent=2)
    )

    print("\n================ LLM OUTPUT ================\n")
    print(run_llm(prompt))


# =========================================================
# 🚀 ENTRY
# =========================================================
if __name__ == "__main__":

    headers = [43, 44, 45, 46]

    for h in headers:
        process(h)