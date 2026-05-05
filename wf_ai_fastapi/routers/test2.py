import json
from typing import Dict, Any, Optional
from datetime import datetime

import process_db as db
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

def build_action_prompt(action: str, context: Dict[str, Any], process_name: str = "Invoice Processing") -> str:
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
# 🔥 RAW FETCH
# =========================================================

def fetch_raw_transaction(header_id: int):

    header = db.get_process_header(header_id)

    items = db.run_query("""
        SELECT id, doc_type, document_url, status, declared_data
        FROM automation_process_item
        WHERE header_id = %s
    """, (header_id,))

    ocr = db.run_query("""
        SELECT item_id, extracted_fields
        FROM workflow_ocr_data
        WHERE header_id = %s
        ORDER BY version DESC
    """, (header_id,))

    workflow = db.run_query("""
        SELECT workflow_id, status, created_at, end_time
        FROM workflow_instance
        WHERE header_id = %s
        ORDER BY created_at DESC
        LIMIT 1
    """, (header_id,))

    workflow = workflow[0] if workflow else None

    activities = []
    if workflow:
        activities = db.run_query("""
            SELECT step_key, task_name, status, start_time, end_time
            FROM workflow_activity_instance
            WHERE workflow_id = %s
            ORDER BY start_time ASC
        """, (workflow["workflow_id"],))

    approvals = db.run_query("""
        SELECT task_name, status, decision, assigned_to
        FROM workflow_approval_task
        WHERE header_id = %s
        ORDER BY created_at DESC
    """, (header_id,))

    erp = db.run_query("""
        SELECT doc_id, approval_status
        FROM erp_crm_documents
        WHERE header_id = %s
        ORDER BY created_at DESC
        LIMIT 1
    """, (header_id,))

    return {
        "header": header,
        "items": items,
        "ocr": ocr,
        "workflow": workflow,
        "activities": activities,
        "approvals": approvals,
        "erp": erp[0] if erp else None
    }


# =========================================================
# 🔥 CORE: CONTEXT COMPILATION (FIXED)
# =========================================================

def compile_context(raw: dict) -> dict:

    header = raw["header"]
    workflow = raw["workflow"]
    erp = raw["erp"]

    # ---------------------------
    # BUSINESS TRUTH
    # ---------------------------
    business_truth = {
        "reference_id": header["reference_id"],
        "vendor": header["declared_data"].get("vendor_name"),
        "invoice_number": header["declared_data"].get("invoice_number")
    }

    # ---------------------------
    # OCR KEY FIELDS (CRITICAL FIX)
    # ---------------------------
    ocr_key_fields = {}

    for row in raw["ocr"]:
        fields = row.get("extracted_fields", {}).get("header", {})
        if fields:
            ocr_key_fields = {
                "invoice_total": fields.get("InvoiceTotal"),
                "invoice_date": fields.get("InvoiceDate"),
                "vendor_name": fields.get("VendorName")
            }
            break

    # ---------------------------
    # STATE NORMALIZATION (FIXED)
    # ---------------------------
    workflow_status = workflow["status"] if workflow else "UNKNOWN"
    approval_status = erp["approval_status"] if erp else None

    # derive final truth
    if workflow_status == "COMPLETED" and approval_status == "APPROVED":
        verification_status = "VERIFIED"
    else:
        verification_status = "PENDING"

    state = {
        "workflow_status": workflow_status,
        "approval_status": approval_status,
        "verification_status": verification_status,
        "erp_posted": erp is not None
    }

    # ---------------------------
    # ACTIVITY TIMELINE
    # ---------------------------
    activity_timeline = [
        f"{a['step_key']} → {a['status']}"
        for a in raw["activities"]
    ]

    # ---------------------------
    # DERIVED SIGNALS (BIG UPGRADE)
    # ---------------------------
    failed_steps = sum(1 for a in raw["activities"] if a["status"] in ("FAILED", "ERROR"))
    total_steps = len(raw["activities"])
    manual_intervention = any(a["decision"] == "MANUAL_APPROVED" for a in raw["approvals"])

    processing_time = None
    if workflow and workflow.get("end_time"):
        processing_time = int(
            (workflow["end_time"] - workflow["created_at"]).total_seconds()
        )

    derived_signals = {
        "total_steps": total_steps,
        "failed_steps": failed_steps,
        "manual_intervention": manual_intervention,
        "stp": not manual_intervention,
        "processing_time_sec": processing_time
    }

    # ---------------------------
    # APPROVAL SUMMARY
    # ---------------------------
    approvals = [
        {
            "decision": a["decision"],
            "actor": a["assigned_to"]
        }
        for a in raw["approvals"]
    ]

    return {
        "business_truth": business_truth,
        "state": state,
        "activity_timeline": activity_timeline,
        "derived_signals": derived_signals,
        "ocr_key_fields": ocr_key_fields,
        "approvals": approvals
    }


# =========================================================
# 🔥 ACTION SHAPING (FIXED)
# =========================================================

def shape_for_action(action: str, ctx: dict) -> dict:

    if action == "what_happened":
        return {
            "business_truth": ctx["business_truth"],
            "activity_timeline": ctx["activity_timeline"],
            "state": ctx["state"]
        }

    if action == "what_matters":
        return {
            "business_truth": ctx["business_truth"],
            "state": ctx["state"],
            "derived_signals": ctx["derived_signals"],
            "ocr_key_fields": ctx["ocr_key_fields"],
            "approvals": ctx["approvals"]
        }

    if action == "what_is_wrong":
        return {
            "activity_timeline": ctx["activity_timeline"],
            "state": ctx["state"],
            "derived_signals": ctx["derived_signals"],
            "ocr_key_fields": ctx["ocr_key_fields"]
        }

    if action == "what_next":
        return {
            "business_truth": ctx["business_truth"],
            "state": ctx["state"],
            "derived_signals": ctx["derived_signals"],
            "approvals": ctx["approvals"]
        }

    return ctx


# =========================================================
# 🔥 PIPELINE
# =========================================================

def build_llm_context(header_id: int, action: str):

    raw = fetch_raw_transaction(header_id)
    print("\n==== RAW ====")
    print(json.dumps(raw, indent=2, default=str))

    compiled = compile_context(raw)

    shaped = shape_for_action(action, compiled)

    return build_action_prompt(action, shaped)


# =========================================================
# 🔥 TEST
# =========================================================

if __name__ == "__main__":

    header_id = 34

    for action in ["where_in_lifecycle", "is_everything_correct", "needs_attention", "root_cause"]:

        prompt = build_llm_context(header_id, action)

        print("\n==============================")
        print(action)
        print("==============================\n")
        print(prompt)