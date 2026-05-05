import json
from typing import Dict, Any


# =========================================================
# 🧠 BASE INSTRUCTION (LLM ROLE)
# =========================================================

BASE_INSTRUCTION = """
You are an enterprise business process analyst AI.

Your role:
- Understand where a transaction is in its lifecycle
- Detect inconsistencies and issues
- Explain what happened in business terms (not technical logs)
- Recommend clear next actions

Rules:
- Analyze ONLY provided structured context
- Do NOT assume missing data
- Use workflow definition to interpret steps
- Use process context to explain lifecycle
- Be precise, structured, and business-friendly

Return STRICT JSON ONLY.
"""


# =========================================================
# 🧭 PROCESS CONTEXT (BUSINESS LIFECYCLE MODEL)
# =========================================================

def build_process_context(process_name: str = "Invoice Processing") -> Dict[str, Any]:
    return {
        "process_name": process_name,
        "lifecycle": [
            "Document received",
            "OCR extraction",
            "Data normalization",
            "Validation",
            "Approval decision",
            "ERP posting",
            "Audit logging"
        ],
        "flow_summary": (
            "Invoice is ingested → OCR extracts data → data is validated → "
            "approval decision is made → approved invoices are posted to ERP → "
            "audit record stored"
        )
    }


# =========================================================
# ⚙️ WORKFLOW DEFINITION (SYSTEM UNDERSTANDING)
# =========================================================

def build_workflow_definition(workflow_name: str = "Invoice Processing Workflow") -> Dict[str, Any]:
    return {
        "name": workflow_name,
        "expected_flow": [
            "01_PREPROCESS_INVOICE",
            "02_OCR",
            "03_NORMALIZE",
            "04_VALIDATE",
            "05_DECISION",
            "06_ERP",
            "08_AUDIT"
        ],
        "step_meaning": {
            "01_PREPROCESS_INVOICE": "Document ingestion and validation",
            "02_OCR": "AI extraction of invoice data",
            "03_NORMALIZE": "Standardization of extracted fields",
            "04_VALIDATE": "Business rule validation",
            "05_DECISION": "Approval or rejection decision",
            "06_ERP": "Posting to ERP system",
            "08_AUDIT": "Audit logging"
        },
        "critical_steps": [
            "04_VALIDATE",
            "05_DECISION",
            "06_ERP"
        ]
    }


# =========================================================
# 🎯 ACTION PROMPTS (5 CORE BUSINESS QUESTIONS)
# =========================================================

ACTION_PROMPTS = {

    # 1. Lifecycle Positioning
    "where_in_lifecycle": """
TASK: Determine where this transaction is in the business process lifecycle.

Focus on:
- Current stage in lifecycle
- Completed vs pending stages
- Alignment with expected workflow

Return JSON:
{
  "current_stage": "",
  "completed_stages": [],
  "pending_stages": [],
  "lifecycle_position": "",
  "confidence": 0.0
}
""",

    # 2. Consistency Check
    "is_everything_correct": """
TASK: Validate whether the transaction is correct and consistent.

Focus on:
- Data consistency across systems
- OCR vs declared vs ERP alignment
- Missing or conflicting data

Return JSON:
{
  "is_consistent": true,
  "issues": [],
  "data_conflicts": [],
  "confidence": 0.0
}
""",

    # 3. Attention / Blocking Detection
    "needs_attention": """
TASK: Identify if this transaction requires attention.

Focus on:
- Stuck or incomplete workflow
- Failed or missing critical steps
- Approval or ERP issues

Return JSON:
{
  "needs_action": true,
  "reason": "",
  "blocking_stage": "",
  "severity": "LOW|MEDIUM|HIGH",
  "confidence": 0.0
}
""",

    # 4. Root Cause Analysis
    "root_cause": """
TASK: Explain why the current state of this transaction occurred.

Focus on:
- Sequence of events
- Failures or delays
- Decision outcomes

Return JSON:
{
  "root_cause": "",
  "contributing_factors": [],
  "confidence": 0.0
}
""",

    # 5. Next Best Action
    "what_next": """
TASK: Recommend the next best actions.

Focus on:
- What user should do next
- Whether system should retry or escalate
- Clear actionable steps

Return JSON:
{
  "next_actions": [],
  "priority": "LOW|MEDIUM|HIGH",
  "automation_opportunities": [],
  "confidence": 0.0
}
"""
}


# =========================================================
# 🧠 PROMPT BUILDER (CORE API LAYER)
# =========================================================

def build_prompt(action: str, context: Dict[str, Any], process_name: str = "Invoice Processing") -> str:
    """
    Build final LLM prompt for AI reasoning API.
    Stateless, deterministic, and workflow-aware.
    """

    if action not in ACTION_PROMPTS:
        raise ValueError(f"Unsupported action: {action}")

    process_context = build_process_context(process_name)
    workflow_definition = build_workflow_definition(process_name)
    task_prompt = ACTION_PROMPTS[action]

    return f"""
{BASE_INSTRUCTION}

{task_prompt}

PROCESS_CONTEXT:
{json.dumps(process_context, indent=2)}

WORKFLOW_DEFINITION:
{json.dumps(workflow_definition, indent=2)}

TRANSACTION_CONTEXT:
{json.dumps(context, indent=2, default=str)}

Return ONLY valid JSON.
"""


# =========================================================
# 🚀 PUBLIC API (USED BY FASTAPI / TEMPORAL / LLM LAYER)
# =========================================================

def get_llm_prompt(header_id: int, action: str, transaction_context: str, process_name: str = "Invoice Processing") -> str:
    """
    Entry point for AI reasoning layer.

    fetch_fn: function that returns full transaction context from DB/Temporal
    """

    raw_context = transaction_context

    return build_prompt(
        action=action,
        context=raw_context,
        process_name=process_name
    )


# =========================================================
# 🧪 LOCAL TEST (OPTIONAL)
# =========================================================

if __name__ == "__main__":

    # Mock function (replace with DB/Temporal fetch)
    transaction_context = {
            "reference_id": "INV-TEST-001",
            "workflow_status": "COMPLETED",
            "approval_status": "APPROVED",
            "erp_posted": True
        }

    for action in ACTION_PROMPTS.keys():
        print("\n" + "=" * 60)
        print(action.upper())
        print("=" * 60)

        prompt = build_prompt(action, transaction_context)
        print(prompt)