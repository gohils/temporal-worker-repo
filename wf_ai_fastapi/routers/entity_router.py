from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List
import psycopg
from psycopg.rows import dict_row
import os
import json
import uuid

router = APIRouter(prefix="/entity", tags=["entity-engine"])

POSTGRES_CONNECTION_STRING = os.getenv("POSTGRES_CONNECTION_STRING")

# =====================================================
# SAFE TABLE WHITELIST (IMPORTANT SECURITY LAYER)
# =====================================================
ALLOWED_TABLES = {
    "vendor_master",
    "customer_master",
    "product_master"
}

# =====================================================
# DB CONNECTION
# =====================================================
def get_conn():
    return psycopg.connect(
        POSTGRES_CONNECTION_STRING,
        row_factory=dict_row
    )

# =====================================================
# MODELS
# =====================================================
class EntityPayload(BaseModel):
    data: Dict[str, Any]


class BulkEntityPayload(BaseModel):
    records: List[Dict[str, Any]]


class EntityConfig(BaseModel):
    entity_name: str
    table_name: str
    pk: str
    config: dict


# =====================================================
# FETCH ENTITY METADATA
# =====================================================
def get_entity_meta(entity: str):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT table_name, pk
            FROM entity_registry
            WHERE entity_name = %s
        """, (entity,))
        meta = cur.fetchone()

    if not meta:
        raise HTTPException(404, f"Entity '{entity}' not found")

    table = meta["table_name"]
    pk = meta["pk"]

    if table not in ALLOWED_TABLES:
        raise HTTPException(400, "Table not allowed")

    return table, pk


# =====================================================
# CREATE / UPDATE ENTITY REGISTRY
# =====================================================
@router.post("/registry")
def upsert_entity_registry(payload: EntityConfig):
    """
    Create or update entity metadata registry

    ```json
    {
      "entity_name": "vendor",
      "table_name": "vendor_master",
      "pk": "vendor_id",
      "config": {
        "ui": "drawer_grid",
        "grid_columns": ["vendor_name", "country", "status"]
      }
    }
    ```
    """

    sql = """
    INSERT INTO entity_registry (entity_name, table_name, pk, config)
    VALUES (%s, %s, %s, %s)
    ON CONFLICT (entity_name)
    DO UPDATE SET
        table_name = EXCLUDED.table_name,
        pk = EXCLUDED.pk,
        config = EXCLUDED.config,
        updated_at = now()
    RETURNING *;
    """

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            sql,
            (
                payload.entity_name,
                payload.table_name,
                payload.pk,
                json.dumps(payload.config),
            ),
        )
        conn.commit()
        return cur.fetchone()


# =====================================================
# GET ENTITY REGISTRY
# =====================================================
@router.get("/registry/{entity_name}")
def get_entity_registry(entity_name: str):
    """
    Get entity configuration and UI metadata

    Example:
    GET /entity/registry/product
    """

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT table_name, pk, config
            FROM entity_registry
            WHERE entity_name = %s
        """, (entity_name,))
        meta = cur.fetchone()

        if not meta:
            raise HTTPException(404, "Entity not found")

        table = meta["table_name"]
        pk = meta["pk"]
        config = meta["config"] or {}

        cur.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = %s
            ORDER BY ordinal_position
        """, (table,))
        columns = cur.fetchall()

    fields = []

    for col in columns:
        name = col["column_name"]
        override = config.get("overrides", {}).get(name, {})

        fields.append({
            "name": name,
            "type": override.get("type", "text"),
            "label": override.get("label", name),
            "options": override.get("options"),
            "required": override.get("required", False)
        })

    return {
        "entity": entity_name,
        "table": table,
        "pk": pk,
        "ui": config.get("ui", "drawer_grid"),
        "grid_columns": config.get(
            "grid_columns",
            [c["column_name"] for c in columns]
        ),
        "fields": fields
    }


# =====================================================
# CREATE RECORD (FIXED PK GENERATION)
# =====================================================
@router.post("/{entity}")
def create_entity(entity: str, payload: EntityPayload):
    """
    Create a new record

    Example:
    ```json
    {
      "data": {
        "vendor_id": "VEND-0007",
        "vendor_name": "ABC Corp",
        "tax_id": "12345",
        "address": "Sydney",
        "payment_terms": "Net 30",
        "currency": "AUD",
        "status": "Active"
      }
    }
    ```

    OR (auto ID allowed):
    ```json
    {
      "data": {
        "vendor_name": "ABC Corp",
        "status": "Active"
      }
    }
    ```
    """

    table, pk = get_entity_meta(entity)
    data = payload.data

    # ==========================
    # AUTO PK GENERATION FIX
    # ==========================
    if pk not in data or not data[pk]:
        prefix = entity[:4].upper()
        data[pk] = f"{prefix}-{uuid.uuid4().hex[:8].upper()}"

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
    """
    Get all records for an entity

    Example:
    GET /entity/vendor
    """

    table, _ = get_entity_meta(entity)

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT * FROM {table} ORDER BY 1 DESC")
        return cur.fetchall()


# =====================================================
# GET SINGLE RECORD
# =====================================================
@router.get("/{entity}/{record_id}")
def get_entity_record(entity: str, record_id: str):
    """
    Get single record by ID

    Example:
    GET /entity/product/PROD-0006
    """

    table, pk = get_entity_meta(entity)

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT * FROM {table} WHERE {pk} = %s",
            (record_id,)
        )
        row = cur.fetchone()

    if not row:
        raise HTTPException(404, "Record not found")

    return row


# =====================================================
# UPDATE RECORD
# =====================================================
@router.put("/{entity}/{record_id}")
def update_entity(entity: str, record_id: str, payload: EntityPayload):
    """
    Update existing record

    Example:
    ```json
    {
      "data": {
        "vendor_name": "Updated Corp",
        "status": "Inactive"
      }
    }
    ```
    """

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
    """
    Delete record

    Example:
    DELETE /entity/vendor/VEND-0001
    """

    table, pk = get_entity_meta(entity)

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"DELETE FROM {table} WHERE {pk} = %s",
            (record_id,)
        )
        conn.commit()

    return {"status": "deleted", "id": record_id}