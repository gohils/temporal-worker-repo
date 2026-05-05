import json
from typing import Dict, Any, Optional
from datetime import datetime

import process_db as db
import json
from typing import Dict, Any


def get_transaction_state(header_id: int) -> dict:
    """
    Single-shot LLM-ready transaction state builder.
    No intermediate compilation layers.
    """

    # =====================================================
    # 1. HEADER (BUSINESS IDENTITY)
    # =====================================================
    header = db.get_process_header(header_id)

    # =====================================================
    # 2. ITEMS (INPUT DOCUMENTS)
    # =====================================================
    items = db.run_query("""
        SELECT id, doc_type, document_url, status, declared_data
        FROM automation_process_item
        WHERE header_id = %s
    """, (header_id,))

    # =====================================================
    # 3. OCR (LATEST EXTRACTED FACTS)
    # =====================================================
    ocr_rows = db.run_query("""
        SELECT item_id, extracted_fields
        FROM workflow_ocr_data
        WHERE header_id = %s
        ORDER BY version DESC
    """, (header_id,))

    ocr_key_fields = {}

    for row in ocr_rows:
        fields = row.get("extracted_fields", {}).get("header", {})
        if fields:
            ocr_key_fields = {
                "invoice_total": fields.get("InvoiceTotal"),
                "invoice_date": fields.get("InvoiceDate"),
                "vendor_name": fields.get("VendorName")
            }
            break

    # =====================================================
    # 4. WORKFLOW INSTANCE (STATE MACHINE SNAPSHOT)
    # =====================================================
    workflow = db.run_query("""
        SELECT workflow_id, status, created_at, end_time
        FROM workflow_instance
        WHERE header_id = %s
        ORDER BY created_at DESC
        LIMIT 1
    """, (header_id,))

    workflow = workflow[0] if workflow else None

    workflow_status = workflow["status"] if workflow else "UNKNOWN"

    # =====================================================
    # 5. ACTIVITIES (EXECUTION HISTORY)
    # =====================================================
    activities = []
    workflow_id = None

    if workflow:
        workflow_id = workflow["workflow_id"]

        activities = db.run_query("""
            SELECT step_key, status
            FROM workflow_activity_instance
            WHERE workflow_id = %s
            ORDER BY start_time ASC
        """, (workflow_id,))

    executed_steps = [
        {
            "step": a["step_key"],
            "status": a["status"]
        }
        for a in activities
    ]

    # =====================================================
    # 6. APPROVALS (HUMAN DECISIONS)
    # =====================================================
    approvals = db.run_query("""
        SELECT decision, assigned_to
        FROM workflow_approval_task
        WHERE header_id = %s
        ORDER BY created_at DESC
    """, (header_id,))

    approval_status = None
    manual_intervention = False

    if approvals:
        approval_status = approvals[0]["decision"]
        manual_intervention = any(
            a["decision"] == "MANUAL_APPROVED" for a in approvals
        )

    # =====================================================
    # 7. ERP STATE (FINAL SYSTEM OF RECORD)
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
    # 8. DERIVED STATE (CRITICAL FOR LLM)
    # =====================================================
    failed_steps = sum(1 for a in activities if a["status"] in ("FAILED", "ERROR"))
    total_steps = len(activities)

    current_step = activities[-1]["step_key"] if activities else "UNKNOWN"

    if workflow_status == "COMPLETED" and erp and erp["approval_status"] == "APPROVED":
        lifecycle_state = "COMPLETED"
    elif failed_steps > 0:
        lifecycle_state = "BLOCKED"
    else:
        lifecycle_state = "IN_PROGRESS"

    # =====================================================
    # 9. FINAL LLM STATE (MINIMAL + DECISION READY)
    # =====================================================
    return {
        "reference_id": header["reference_id"],
        "workflow_id": workflow_id,

        # -----------------------------
        # CORE STATE
        # -----------------------------
        "state": {
            "workflow_status": workflow_status,
            "approval_status": approval_status,
            "erp_posted": erp is not None,
            "lifecycle_state": lifecycle_state
        },

        # -----------------------------
        # CURRENT POSITION
        # -----------------------------
        "position": {
            "current_step": current_step,
            "failed_steps": failed_steps,
            "total_steps": total_steps,
            "manual_intervention": manual_intervention
        },

        # -----------------------------
        # EXECUTION HISTORY
        # -----------------------------
        "execution_history": executed_steps,

        # -----------------------------
        # BUSINESS FACTS
        # -----------------------------
        "business": {
            "vendor": header["declared_data"].get("vendor_name"),
            "invoice_number": header["declared_data"].get("invoice_number")
        },

        # -----------------------------
        # OCR FACTS
        # -----------------------------
        "ocr": ocr_key_fields,

        # -----------------------------
        # ERP FACTS
        # -----------------------------
        "erp": erp
    }

# =========================================================
# 🔥 TEST
# =========================================================

if __name__ == "__main__":

    header_id = 34
    prompt = get_transaction_state(header_id)
    print("==============================\n")
    print(prompt)
    print("\n==============================")