from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List
import psycopg
from psycopg.rows import dict_row
import os
import uuid

router = APIRouter(prefix="/entity", tags=["entity-engine"])

POSTGRES_CONNECTION_STRING = os.getenv("POSTGRES_CONNECTION_STRING")

# =====================================================
# SECURITY: ALLOWED TABLES ONLY (prevent SQL abuse)
# =====================================================
ALLOWED_TABLES = {
    "vendor_master",
    "customer_master",
    "product_master"
}

# =====================================================
# DB CONNECTION FACTORY
# =====================================================
def get_conn():
    return psycopg.connect(
        POSTGRES_CONNECTION_STRING,
        row_factory=dict_row
    )


# =====================================================
# REQUEST MODELS
# =====================================================
class EntityPayload(BaseModel):
    data: Dict[str, Any]


class BulkEntityPayload(BaseModel):
    records: List[Dict[str, Any]]


# =====================================================
# ENTITY META RESOLVER (TABLE + PK)
# Uses PostgreSQL system catalog (no registry dependency)
# =====================================================
def get_entity_meta(entity: str):

    # # 1. Validate allowed table
    # if entity not in ALLOWED_TABLES:
    #     raise HTTPException(400, "Table not allowed")

    table = entity

    # 2. Fetch primary key from PostgreSQL system tables
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT a.attname AS pk
            FROM pg_index i
            JOIN pg_attribute a
              ON a.attrelid = i.indrelid
             AND a.attnum = ANY(i.indkey)
            WHERE i.indrelid = %s::regclass
              AND i.indisprimary
        """, (table,))
        pk_row = cur.fetchone()

    if not pk_row:
        raise HTTPException(400, "Primary key not found")

    return table, pk_row["pk"]


# =====================================================
# CREATE RECORD
# - auto-generates PK if missing
# =====================================================
@router.post("/{entity}")
def create_entity(entity: str, payload: EntityPayload):

    table, pk = get_entity_meta(entity)
    data = payload.data

    # Auto-generate primary key if missing
    if not data.get(pk):
        data[pk] = f"{entity[:4].upper()}-{uuid.uuid4().hex[:8].upper()}"

    cols = list(data.keys())
    values = list(data.values())

    sql = f"""
        INSERT INTO {table} ({",".join(cols)})
        VALUES ({",".join(["%s"] * len(cols))})
        RETURNING *
    """

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, values)
        conn.commit()
        return cur.fetchone()


# =====================================================
# LIST ALL RECORDS
# =====================================================
@router.get("/{entity}")
def list_entity(entity: str):

    table, _ = get_entity_meta(entity)

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT * FROM {table} ORDER BY 1 DESC")
        return cur.fetchall()


# =====================================================
# GET SINGLE RECORD BY PRIMARY KEY
# =====================================================
@router.get("/{entity}/{record_id}")
def get_entity_record(entity: str, record_id: str):

    table, pk = get_entity_meta(entity)

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT * FROM {table} WHERE {pk} = %s", (record_id,))
        row = cur.fetchone()

    if not row:
        raise HTTPException(404, "Record not found")

    return row


# =====================================================
# UPDATE RECORD (partial update supported)
# =====================================================
@router.put("/{entity}/{record_id}")
def update_entity(entity: str, record_id: str, payload: EntityPayload):

    table, pk = get_entity_meta(entity)
    data = payload.data

    set_clause = ", ".join([f"{k} = %s" for k in data.keys()])
    values = list(data.values())

    sql = f"""
        UPDATE {table}
        SET {set_clause}
        WHERE {pk} = %s
        RETURNING *
    """

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, values + [record_id])
        conn.commit()
        return cur.fetchone()


# =====================================================
# DELETE RECORD
# =====================================================
@router.delete("/{entity}/{record_id}")
def delete_entity(entity: str, record_id: str):

    table, pk = get_entity_meta(entity)

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(f"DELETE FROM {table} WHERE {pk} = %s", (record_id,))
        conn.commit()

    return {"status": "deleted", "id": record_id}


# =====================================================
# BULK REPLACE (ALV GRID SAVE)
# - deletes all rows
# - inserts fresh dataset
# =====================================================
@router.post("/{entity}/replace")
def replace(entity: str, payload: BulkEntityPayload):

    table, pk = get_entity_meta(entity)

    if not payload.records:
        raise HTTPException(400, "Empty payload")

    inserted = 0

    with get_conn() as conn, conn.cursor() as cur:

        # 1. wipe table (full replace semantics)
        cur.execute(f"DELETE FROM {table}")

        # 2. insert all rows
        for row in payload.records:

            if not isinstance(row, dict):
                continue

            # remove empty/null values
            cleaned = {k: v for k, v in row.items() if v not in (None, "")}

            if not cleaned:
                continue

            cols = list(cleaned.keys())
            vals = list(cleaned.values())

            col_sql = ",".join(f'"{c}"' for c in cols)
            val_sql = ",".join(["%s"] * len(cols))

            sql = f"INSERT INTO {table} ({col_sql}) VALUES ({val_sql})"

            cur.execute(sql, vals)
            inserted += 1

        conn.commit()

    return {
        "status": "replaced",
        "rows_received": len(payload.records),
        "rows_inserted": inserted
    }