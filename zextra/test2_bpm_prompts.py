import json
from typing import Dict, Any
import json
from typing import Dict, Any

import wf_ai_fastapi.routers.process_db as db


def build_transaction_state(header_id: int) -> dict:
    header = db.get_process_header(header_id)

    workflow = db.run_query("""
        SELECT workflow_id, status
        FROM workflow_instance
        WHERE header_id = %s
        ORDER BY created_at DESC
        LIMIT 1
    """, (header_id,))

    workflow = workflow[0] if workflow else None
    workflow_id = workflow["workflow_id"] if workflow else None

    activities = db.run_query("""
        SELECT step_key, status
        FROM workflow_activity_instance
        WHERE workflow_id = %s
        ORDER BY start_time ASC
    """, (workflow_id,)) if workflow_id else []

    failed_steps = sum(a["status"] in ("FAILED", "ERROR") for a in activities)
    completed_steps = [a["step_key"] for a in activities if a["status"] == "COMPLETED"]

    erp = db.run_query("""
        SELECT approval_status
        FROM erp_crm_documents
        WHERE header_id = %s
        ORDER BY created_at DESC
        LIMIT 1
    """, (header_id,))

    erp = erp[0] if erp else None

    lifecycle_state = "IN_PROGRESS"
    if erp and erp["approval_status"] == "APPROVED" and failed_steps == 0:
        lifecycle_state = "COMPLETED"
    elif failed_steps > 0:
        lifecycle_state = "BLOCKED"

    return {
        "reference_id": header["reference_id"],
        "workflow_type": header["workflow_type"],

        "state": {
            "lifecycle": lifecycle_state,
            "current_step": activities[-1]["step_key"] if activities else None,
            "failed_steps": failed_steps,
            "completed_steps": completed_steps,
        },

        "facts": {
            "vendor": header["declared_data"].get("vendor_name"),
            "invoice": header["declared_data"].get("invoice_number"),
        },

        "erp": erp,
        "trace": activities
    }

def build_llm_context(action: str, base: dict) -> dict:

    if action == "summary":
        return {
            "state": base["state"],
            "facts": base["facts"]
        }

    if action == "root_cause":
        return {
            "state": base["state"],
            "trace": base["trace"]
        }

    if action == "what_next":
        return {
            "state": base["state"],
            "erp": base["erp"]
        }

    return {
        "state": base["state"]
    }

BASE_INSTRUCTION = """
You are a business process analyst assistant.

You DO NOT compute state.
You DO NOT detect system issues.

You ONLY:
- explain what system already determined
- summarize business meaning
- propose human-level actions

Rules:
- Never infer missing system state
- Never contradict input data
- Keep output short and operational
"""

ACTION_PROMPTS = {

"process_status": """
Give a manager-ready status of this transaction.

Focus:
- current lifecycle position
- what is completed
- what is pending
- current step meaning

Return JSON:
{
  "analysis": {},
  "business_summary": ""
}
""",

"risk_assessment": """
Identify risks, blockers, or exceptions.

Focus:
- failed steps
- stuck state
- SLA risk
- manual intervention impact

Return JSON:
{
  "analysis": {
    "risk_level": "",
    "blocking_reason": "",
    "confidence": 0.0
  },
  "business_summary": ""
}
""",

"data_integrity": """
Check consistency across all systems.

Focus:
- ERP vs declared vs trace mismatches
- missing or conflicting data

Return JSON:
{
  "analysis": {
    "is_consistent": true,
    "issues": [],
    "confidence": 0.0
  },
  "business_summary": ""
}
""",

"root_cause": """
Explain why the transaction reached this state.

Focus:
- trace-based reasoning
- key transitions
- failure or delay points

Return JSON:
{
  "analysis": {
    "root_cause": "",
    "confidence": 0.0
  },
  "business_summary": ""
}
""",

"next_best_action": """
Recommend exact next business actions.

Focus:
- human actions
- escalation triggers
- automation opportunities

Return JSON:
{
  "analysis": {
    "next_actions": [],
    "priority": ""
  },
  "business_summary": ""
}
"""
}

def build_prompt(action: str, context: dict) -> str:
    return f"""
{BASE_INSTRUCTION}

TASK:
{ACTION_PROMPTS[action]}

CONTEXT:
{json.dumps(context, indent=2)}

Return JSON only.
"""


# =========================================================
# 🔧 CORE EXECUTION (MIRRORS FASTAPI ENDPOINT)
# =========================================================
def ai_reasoning(req: Dict[str, Any]):

    import os
    from openai import OpenAI

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    action = req["action"]
    header_id = req["context"]["headerId"]

    base = build_transaction_state(header_id)
    context = build_llm_context(action, base)

    prompt = build_prompt(action, context)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": BASE_INSTRUCTION},
            {"role": "user", "content": prompt},
        ],
        temperature=0
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
# 🚀 ENTRY POINT
# =========================================================

if __name__ == "__main__":

    # testing single action for faster iteration
    base_req = {
        "action": "where_in_lifecycle",
        "context": {
            "workflowId": "INV-20260414-B125B3-202604141803",
            "headerId": 34,
            "referenceId": "INV-20260414-B125B3"
        },
        "options": {
            "model": "gpt-4o-mini"
        }
    }

    # response = ai_reasoning(base_req)

    # print("\n================ SINGLE TEST =================\n")
    # print(json.dumps(response, indent=2))    

    print("\n================ ALL ACTIONS =================\n")

    for action in ACTION_PROMPTS.keys():
        print("\n" + "=" * 80)
        print(f"ACTION: {action}")
        print("=" * 80)

        base_req["action"] = action

        result = ai_reasoning(base_req)

        print(json.dumps(result, indent=2))