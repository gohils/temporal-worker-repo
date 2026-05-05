import json
from typing import Dict, Any, Optional

import process_db as db


# =========================================================
# 🔥 LATEST WORKFLOW FETCH (CLEAN)
# =========================================================
def get_latest_workflow(header_id: int) -> Optional[Dict[str, Any]]:
    rows = db.run_query("""
        SELECT *
        FROM workflow_instance
        WHERE header_id = %s
        ORDER BY created_at DESC
        LIMIT 1
    """, (header_id,))

    return rows[0] if rows else None


# =========================================================
# 🔥 LATEST WORKFLOW ACTIVITIES (FIXED)
# =========================================================
def get_latest_workflow_activities(workflow_id: str):
    return db.run_query("""
        SELECT activity_id, step_key, task_name, activity_type, activity_group,
               workflow_type, header_id, item_id,
               status, start_time, end_time, created_at
        FROM workflow_activity_instance
        WHERE workflow_id = %s
        ORDER BY start_time ASC
    """, (workflow_id,))


# =========================================================
# 🔥 MAIN SNAPSHOT BUILDER (FIXED + CLEANED)
# =========================================================
def build_transaction_snapshot(header_id: int):

    # --------------------------
    # HEADER (business truth)
    # --------------------------
    header = db.get_process_header(header_id)

    # keep only relevant fields
    header = {
        "id": header["id"],
        "reference_id": header["reference_id"],
        "workflow_type": header["workflow_type"],
        "process_name": header["process_name"],
        "process_group": header["process_group"],
        "declared_data": header["declared_data"],
        "verification_status": header["verification_status"],
        "created_at": header["created_at"],
    }

    # --------------------------
    # ITEMS (business documents)
    # --------------------------
    items = db.run_query("""
        SELECT id, header_id, doc_type, document_id, document_url,
               declared_data, verification_status, status
        FROM automation_process_item
        WHERE header_id = %s
    """, (header_id,))

    # --------------------------
    # OCR (minimal + latest only)
    # --------------------------
    ocr_rows = db.run_query("""
        SELECT item_id, extracted_fields, status, version
        FROM workflow_ocr_data
        WHERE header_id = %s
        ORDER BY version DESC
    """, (header_id,))

    ocr_map = {}
    for row in ocr_rows:
        if row["item_id"] not in ocr_map:
            ocr_map[row["item_id"]] = {
                "fields": row["extracted_fields"],
                "status": row["status"]
            }

    enriched_items = []
    for item in items:
        ocr = ocr_map.get(item["id"])

        enriched_items.append({
            "id": item["id"],
            "doc_type": item["doc_type"],
            "document_url": item["document_url"],
            "status": item["status"],
            "ocr": ocr
        })

    # --------------------------
    # LATEST WORKFLOW
    # --------------------------
    latest_workflow = get_latest_workflow(header_id)

    workflow_activities = None
    if latest_workflow:
        workflow_activities = get_latest_workflow_activities(
            latest_workflow["workflow_id"]
        )

    # reduce activity noise
    if workflow_activities:
        workflow_activities = [
            {
                "step_key": a["step_key"],
                "task_name": a["task_name"],
                "status": a["status"],
                "start_time": a["start_time"],
                "end_time": a["end_time"]
            }
            for a in workflow_activities
        ]

    # --------------------------
    # APPROVALS (latest only)
    # --------------------------
    approvals = db.run_query("""
        SELECT task_name, task_type, status, decision,
               assigned_to, comments, completed_at
        FROM workflow_approval_task
        WHERE header_id = %s
        ORDER BY created_at DESC
        LIMIT 5
    """, (header_id,))

    # --------------------------
    # ERP (summary only)
    # --------------------------
    erp = db.run_query("""
        SELECT doc_id, doc_type, approval_status,
               approved_by, created_at
        FROM erp_crm_documents
        WHERE header_id = %s
        ORDER BY created_at DESC
        LIMIT 1
    """, (header_id,))

    if erp:
        erp = erp[0]

    # --------------------------
    # FINAL SNAPSHOT
    # --------------------------
    return {
        "header": header,
        "items": enriched_items,
        "latest_workflow": latest_workflow,
        "workflow_activities": workflow_activities,
        "approvals": approvals,
        "erp": erp
    }

# =========================================================
# 🔥 TEST RUN
# =========================================================
if __name__ == "__main__":

    test_header_id = 34

    snapshot = build_transaction_snapshot(test_header_id)

    print(json.dumps(snapshot, indent=2, default=str))