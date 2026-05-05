import json
from typing import Dict, Any, Optional
import process_db as db


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
# 🔥 TEST
# =========================================================
if __name__ == "__main__":

    header_id = 34

    state = get_transaction_state(header_id)

    print(json.dumps(state, indent=2, default=str))