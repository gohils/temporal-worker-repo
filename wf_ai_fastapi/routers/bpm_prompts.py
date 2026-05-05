import json
from typing import Dict, Any

import wf_ai_fastapi.routers.process_db as db


def get_transaction_state(header_id: int) -> dict:
    """
    LLM-optimized transaction state
    minimal, causal, decision-ready
    """

    # =====================================================
    # 1. HEADER
    # =====================================================
    header = db.get_process_header(header_id)

    reference_id = header["reference_id"]
    workflow_type = header["workflow_type"]

    # =====================================================
    # 2. WORKFLOW INSTANCE
    # =====================================================
    workflow = db.run_query("""
        SELECT workflow_id, status, created_at, end_time
        FROM workflow_instance
        WHERE header_id = %s
        ORDER BY created_at DESC
        LIMIT 1
    """, (header_id,))

    workflow = workflow[0] if workflow else None
    workflow_id = workflow["workflow_id"] if workflow else None
    workflow_status = workflow["status"] if workflow else "UNKNOWN"

    # =====================================================
    # 3. ACTIVITIES (CAUSAL TRACE - COMPRESSED)
    # =====================================================
    activities = []

    if workflow_id:
        rows = db.run_query("""
            SELECT step_key, status
            FROM workflow_activity_instance
            WHERE workflow_id = %s
            ORDER BY start_time ASC
        """, (workflow_id,))

        activities = [
            {
                "step": r["step_key"],
                "status": r["status"]
            }
            for r in rows
        ]

    current_step = activities[-1]["step"] if activities else "UNKNOWN"
    failed_steps = sum(1 for a in activities if a["status"] in ("FAILED", "ERROR"))

    manual_intervention = db.run_query("""
        SELECT COUNT(*) as cnt
        FROM workflow_approval_task
        WHERE header_id = %s AND decision = 'MANUAL_APPROVED'
    """, (header_id,))[0]["cnt"] > 0

    # =====================================================
    # 4. APPROVAL STATE
    # =====================================================
    approval = db.run_query("""
        SELECT decision
        FROM workflow_approval_task
        WHERE header_id = %s
        ORDER BY created_at DESC
        LIMIT 1
    """, (header_id,))

    approval_decision = approval[0]["decision"] if approval else None

    # =====================================================
    # 5. ERP STATE
    # =====================================================
    erp = db.run_query("""
        SELECT doc_id, approval_status
        FROM erp_crm_documents
        WHERE header_id = %s
        ORDER BY created_at DESC
        LIMIT 1
    """, (header_id,))

    erp = erp[0] if erp else None

    # =====================================================
    # 6. OCR (LATEST FACTS ONLY)
    # =====================================================
    ocr = db.run_query("""
        SELECT extracted_fields
        FROM workflow_ocr_data
        WHERE header_id = %s
        ORDER BY version DESC
        LIMIT 1
    """, (header_id,))

    ocr_fields = {}

    if ocr:
        h = ocr[0]["extracted_fields"].get("header", {})
        ocr_fields = {
            "invoice_total": h.get("InvoiceTotal"),
            "invoice_date": h.get("InvoiceDate"),
            "vendor_name": h.get("VendorName")
        }

    # =====================================================
    # 7. DERIVED LIFECYCLE STATE (CRITICAL)
    # =====================================================
    lifecycle_state = "IN_PROGRESS"

    if workflow_status == "COMPLETED" and erp and erp["approval_status"] == "APPROVED":
        lifecycle_state = "COMPLETED"
    elif failed_steps > 0:
        lifecycle_state = "BLOCKED"

    # =====================================================
    # 8. FINAL LLM STATE (OPTIMAL)
    # =====================================================
    return {
        # -------------------------
        # IDENTITY
        # -------------------------
        "reference_id": reference_id,
        "workflow_type": workflow_type,

        # -------------------------
        # LIFECYCLE (SINGLE SOURCE OF TRUTH)
        # -------------------------
        "lifecycle": {
            "state": lifecycle_state,
            "workflow_status": workflow_status,
            "current_step": current_step,
            "failed_steps": failed_steps,
            "manual_intervention": manual_intervention
        },

        # -------------------------
        # CAUSAL TRACE (COMPRESSED)
        # -------------------------
        "execution_trace": activities,

        # -------------------------
        # BUSINESS FACTS
        # -------------------------
        "business": {
            "vendor": header["declared_data"].get("vendor_name"),
            "invoice_number": header["declared_data"].get("invoice_number")
        },

        # -------------------------
        # OCR FACTS
        # -------------------------
        "ocr": ocr_fields,

        # -------------------------
        # ERP FACTS
        # -------------------------
        "erp": erp,

        # -------------------------
        # DECISION SIGNAL (ONLY 1 FIELD)
        # -------------------------
        "approval": approval_decision
    }

# =========================================================
# 🧠 BASE INSTRUCTION (LLM ROLE)
# =========================================================

BASE_INSTRUCTION = """
You are an enterprise business process analyst AI.

Your role:
- Understand where a transaction is in its lifecycle
- Detect inconsistencies and issues
- Explain what happened in business terms
- Produce structured analysis AND business summary

Rules:
- Analyze ONLY provided structured context
- Do NOT assume missing data
- Be precise and deterministic
- Use workflow definition strictly

OUTPUT REQUIREMENTS (STRICT):

1. Always return valid JSON only

2. Every response MUST include:
   - structured analysis (per task schema)
   - business_summary

BUSINESS SUMMARY RULES:
- 2 to 4 short sentences only
- no adjectives (e.g. "successful", "robust", "flawless")
- no technical terms (OCR, workflow_id, API, DB)
- focus on:
  1. current status
  2. what is completed
  3. what matters next (if anything)
- neutral, operational tone
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
  "analysis": {
    "current_stage": "",
    "completed_stages": [],
    "pending_stages": [],
    "lifecycle_position": "",
    "confidence": 0.0
  },
  "business_summary": ""
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
  "analysis": {
    "is_consistent": true,
    "issues": [],
    "data_conflicts": [],
    "confidence": 0.0
  },
  "business_summary": ""
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
  "analysis": {
    "needs_action": true,
    "reason": "",
    "blocking_stage": "",
    "severity": "LOW|MEDIUM|HIGH",
    "confidence": 0.0
  },
  "business_summary": ""
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
  "analysis": {
    "root_cause": "",
    "contributing_factors": [],
    "confidence": 0.0
  },
  "business_summary": ""
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
  "analysis": {
    "next_actions": [],
    "priority": "LOW|MEDIUM|HIGH",
    "automation_opportunities": [],
    "confidence": 0.0
  },
  "business_summary": ""
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


