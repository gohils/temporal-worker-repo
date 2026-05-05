import json
from typing import Dict, Any
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
,
"default_summarization": """
TASK: Summarize the most important aspects of this transaction.

Focus on:
- Current state significance
- Key risks or blockers
- Most important business facts

Return JSON:
{
  "analysis": {
    "key_points": [],
    "risk_level": "LOW|MEDIUM|HIGH",
    "important_fields": [],
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

def build_action_context(action: str, base: dict) -> dict:

    if action == "where_in_lifecycle":
        return {
            "lifecycle": base["lifecycle"],
            "execution_trace": base["execution_trace"]
        }

    elif action == "root_cause":
        return {
            "execution_trace": base["execution_trace"],
            "failed_steps": base["lifecycle"]["failed_steps"],
            "current_step": base["lifecycle"]["current_step"]
        }

    elif action == "what_next":
        return {
            "current_step": base["lifecycle"]["current_step"],
            "approval": base["approval"],
            "erp": base["erp"]
        }

    elif action == "is_everything_correct":
        return {
            "business": base["business"],
            "ocr": base["ocr"],
            "erp": base["erp"]
        }

    elif action == "needs_attention":
        return {
            "lifecycle": base["lifecycle"],
            "failed_steps": base["lifecycle"]["failed_steps"],
            "manual_intervention": base["lifecycle"]["manual_intervention"]
        }

    return base


# =========================================================
# 🔧 CORE EXECUTION (MIRRORS FASTAPI ENDPOINT)
# =========================================================
def ai_reasoning(req: Dict[str, Any]) -> Dict[str, Any]:
    """
    FastAPI-equivalent execution layer (sync version)

    Expected req:
    {
        "action": "...",
        "context": {...},
        "options": {...}
    }
    """

    import os
    from openai import OpenAI

    llm_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    try:
        # -----------------------------
        # 1. SAFE INPUT EXTRACTION
        # -----------------------------
        action = req.get("action")
        context = req.get("context", {})
        options = req.get("options", {})

        header_id = context.get("headerId")

        if not action:
            raise ValueError("Missing action")

        if not header_id:
            raise ValueError("Missing headerId in context")

        # -----------------------------
        # 2. BUILD CONTEXT
        # -----------------------------
        # transaction_state_context = get_transaction_state(header_id)
        base_context = get_transaction_state(header_id)
        filtered_context = build_action_context(action, base_context)
        # -----------------------------
        # 3. BUILD PROMPT
        # -----------------------------
        final_prompt = build_prompt(action, filtered_context)

        # -----------------------------
        # 4. LLM CALL
        # -----------------------------
        response = llm_client.chat.completions.create(
            model=options.get("model", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": "Return ONLY valid JSON."},
                {"role": "user", "content": final_prompt},
            ],
            temperature=0
        )

        raw = response.choices[0].message.content

        # -----------------------------
        # 5. SAFE PARSING (CRITICAL)
        # -----------------------------
        try:
            parsed = json.loads(raw)

            # enforce structure
            if "analysis" not in parsed:
                parsed["analysis"] = {}

            if "business_summary" not in parsed:
                parsed["business_summary"] = ""

        except Exception:
            parsed = {
                "analysis": {},
                "business_summary": "",
                "error": "invalid_json",
                "raw_response": raw
            }

        # -----------------------------
        # 6. RESPONSE SHAPING
        # -----------------------------
        return {
            "action": action,
            "final_prompt": final_prompt,
            "result": parsed,
            "raw_response": raw,
            "confidence": parsed.get("analysis", {}).get("confidence")
        }

    except Exception as e:
        return {
            "action": req.get("action"),
            "final_prompt": None,
            "result": {
                "analysis": {},
                "business_summary": "",
                "error": str(e)
            },
            "raw_response": None,
            "confidence": None
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