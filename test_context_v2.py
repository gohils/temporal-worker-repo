import json
from typing import Dict, Any, Optional
import wf_ai_fastapi.routers.process_db as db

from datetime import datetime, date

def json_serializer(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()  # ✅ clean ISO format
    return str(obj)


# =========================================================
# 🔥 LATEST WORKFLOW (ONLY STATE, NOT HISTORY)
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


# =========================================================
# 🔥 LATEST ACTIVITY (ONLY LAST STEP = SIGNAL)
# =========================================================
def get_latest_activity(workflow_id: str):
    rows = db.run_query("""
        SELECT step_key, task_name, status
        FROM workflow_activity_instance
        WHERE workflow_id = %s
        ORDER BY start_time DESC
        LIMIT 1
    """, (workflow_id,))

    return rows[0] if rows else None


# =========================================================
# 🔥 OCR SIGNAL (LATEST ONLY + FULL DOC INTELLIGENCE)
# =========================================================
def get_latest_ocr(item_id: int):
    rows = db.run_query("""
        SELECT extracted_fields, status
        FROM workflow_ocr_data
        WHERE item_id = %s
        ORDER BY version DESC
        LIMIT 1
    """, (item_id,))

    return rows[0] if rows else None


# =========================================================
# 🔥 ERP SIGNAL (FINAL STATE ONLY)
# =========================================================
def get_latest_erp(header_id: int):
    rows = db.run_query("""
        SELECT doc_id, doc_type,
               approval_status, approved_by, created_at
        FROM erp_crm_documents
        WHERE header_id = %s
        ORDER BY created_at DESC
        LIMIT 1
    """, (header_id,))

    return rows[0] if rows else None


# =========================================================
# 🔥 APPROVAL SIGNAL (LATEST DECISION ONLY)
# =========================================================
def get_latest_approval(header_id: int):
    rows = db.run_query("""
        SELECT task_name, status, decision,
               assigned_to, comments, completed_at
        FROM workflow_approval_task
        WHERE header_id = %s
        ORDER BY created_at DESC
        LIMIT 1
    """, (header_id,))

    return rows[0] if rows else None


# =========================================================
# 🔥 HEADER (ONLY WHAT LLM NEEDS FOR REASONING)
# =========================================================
def get_header(header_id: int):
    h = db.get_process_header(header_id)

    return {
        "id": h["id"],
        "reference_id": h["reference_id"],
        "workflow_type": h["workflow_type"],
        "process_name": h["process_name"],
        "process_group": h["process_group"],
        "declared_data": h["declared_data"],
        "verification_status": h["verification_status"]
    }


# =========================================================
# 🔥 ITEMS (ONLY ACTIVE + CURRENT STATE)
# =========================================================
def get_items(header_id: int):
    rows = db.run_query("""
        SELECT id, doc_type, document_url, status
        FROM automation_process_item
        WHERE header_id = %s
        AND is_active = TRUE
    """, (header_id,))

    items = []

    for r in rows:
        ocr = get_latest_ocr(r["id"])

        items.append({
            "item_id": r["id"],
            "doc_type": r["doc_type"],
            "status": r["status"],
            "document_url": r["document_url"],

            # 🔥 FULL OCR SIGNAL (kept intact but latest only)
            "ocr": ocr["extracted_fields"] if ocr else None
        })

    return items


# =========================================================
# 🔥 MAIN SIGNAL SNAPSHOT BUILDER (CLEAN MVP1 VERSION)
# =========================================================
def build_transaction_snapshot(header_id: int):

    # --------------------------
    # 1. HEADER SIGNAL
    # --------------------------
    header = get_header(header_id)

    # --------------------------
    # 2. ITEM + OCR SIGNAL
    # --------------------------
    items = get_items(header_id)

    # --------------------------
    # 3. WORKFLOW SIGNAL (LATEST ONLY)
    # --------------------------
    workflow = get_latest_workflow(header_id)

    activity = None
    if workflow:
        activity = get_latest_activity(workflow["workflow_id"])

    # --------------------------
    # 4. APPROVAL + ERP SIGNAL
    # --------------------------
    approval = get_latest_approval(header_id)
    erp = get_latest_erp(header_id)

    # --------------------------
    # 🔥 FINAL LLM-OPTIMIZED SNAPSHOT
    # --------------------------
    return {
        "header": header,
        "items": items,

        # SYSTEM STATE (CRITICAL FOR ALL BUTTONS)
        "state": {
            "workflow": workflow,
            "last_activity": activity,
            "approval": approval,
            "erp": erp
        }
    }

def extract_business_signal(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    header = snapshot["header"]
    items = snapshot.get("items", [])
    state = snapshot.get("state", {})

    declared = header.get("declared_data", {}) or {}

    # 🔥 Prefer OCR header if available
    ocr_header = None
    if items and items[0].get("ocr"):
        ocr_header = items[0]["ocr"].get("header")

    return {
        "transaction_id": header.get("reference_id"),
        "process_name": header.get("process_name"),
        "workflow_type": header.get("workflow_type"),

        # 🔥 BUSINESS DATA (PRIORITY ORDER)
        "vendor_name": (
            (ocr_header or {}).get("VendorName")
            or declared.get("vendor_name")
        ),
        "invoice_total": (
            (ocr_header or {}).get("InvoiceTotal")
            or declared.get("amount")
        ),
        "invoice_number": (
            (ocr_header or {}).get("InvoiceId")
            or declared.get("invoice_number")
        ),

        # 🔥 SYSTEM STATE
        "workflow_status": state.get("workflow", {}).get("status"),
        "current_step": state.get("last_activity", {}).get("step_key"),
        "approval_status": state.get("approval", {}).get("status"),
        "approval_decision": state.get("approval", {}).get("decision"),
        "approved_by": state.get("approval", {}).get("assigned_to"),
        "erp_doc_id": state.get("erp", {}).get("doc_id"),
    }

# =========================================================
# 🔧 CORE EXECUTION (MIRRORS FASTAPI ENDPOINT)
# =========================================================
BASE_INSTRUCTION = """
You are a business operations assistant.

You MUST generate a concise, structured, human-readable response for a business user.

STRICT RULES:
- Always include transaction_id, vendor_name, and invoice_total
- Never omit key business identifiers
- Never add assumptions
- Do not narrate process history
- Do not explain system internals
- Focus only on: current state, completed steps, and next action

OUTPUT FORMAT (STRICT):

📍 Lifecycle Status
<one line with transaction_id, vendor, amount, lifecycle stage>

---

🔄 Process Path
<fixed pipeline string>
<status ticks>

---

✅ What’s Completed (No need to recheck)
<bullet list based on actual completed signals>

---

🟢 Current Status
<blocking or completed>

---

▶️ Next Action
<clear action>

---

🔒 Confidence
<short evidence-based statement>
"""

def ai_reasoning(snapshot: Dict[str, Any]):

    import os
    from openai import OpenAI

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    signal = extract_business_signal(snapshot)

    final_prompt = f"""
Business Signal:
{json.dumps(signal, indent=2)}

Instructions:
Generate lifecycle status response.
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": BASE_INSTRUCTION},
            {"role": "user", "content": final_prompt},
        ],
        temperature=0
    )

    return response.choices[0].message.content
    

# =========================================================
# 🚀 ENTRY POINT
# =========================================================

if __name__ == "__main__":


    # testing single action for faster iteration
    # headers = [31, 32, 33, 34, 35, 36]
    headers = [34]
    for header_id in headers:
        response = build_transaction_snapshot(header_id)
        print(f"\n================ TEST FOR HEADER {header_id} =================\n")
        print(response)
        print("\n================ LLM REASONING =================\n")
        llm_response = ai_reasoning(response)
        print(llm_response)