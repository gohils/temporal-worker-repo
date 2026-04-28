from fastapi import APIRouter, HTTPException, Body, Query
import psycopg
from psycopg.rows import dict_row
import os

router = APIRouter(prefix="/txn", tags=["transaction-engine"])

POSTGRES_CONNECTION_STRING = os.getenv("POSTGRES_CONNECTION_STRING")

# -----------------------------
# DB CONNECTION
# -----------------------------
def get_conn():
    return psycopg.connect(
        POSTGRES_CONNECTION_STRING,
        row_factory=dict_row
    )

# -----------------------------
# RESOLVE TABLES (Convention)
# -----------------------------
def resolve_tables(entity: str):
    return {
        "header_table": f"{entity}_header",
        "item_table": f"{entity}_items",
        "fk_field": f"{entity}_id",
        "pk": "id"
    }

# -----------------------------
# CREATE TRANSACTION
# -----------------------------
@router.post("/{entity}")
def create_transaction(entity: str, payload: dict = Body(...)):
    """
    Create transaction (header + items)

    ```json
    {
      "header": {
        "invoice_no": "INV-1001",
        "vendor": "Apple India Pvt Ltd",
        "date": "2026-04-10",
        "status": "Draft"
      },
      "items": [
        {
          "item": "MacBook Pro",
          "qty": 2,
          "price": 2500,
          "total": 5000
        },
        {
          "item": "iPhone",
          "qty": 3,
          "price": 1200,
          "total": 3600
        }
      ]
    }
    ```
    """
    meta = resolve_tables(entity)

    header = payload.get("header", {})
    items = payload.get("items", [])

    if not header:
        raise HTTPException(400, "Header is required")

    with get_conn() as conn, conn.cursor() as cur:

        # -------- INSERT HEADER --------
        cols = list(header.keys())
        vals = list(header.values())

        cur.execute(
            f"""
            INSERT INTO {meta['header_table']} ({", ".join(cols)})
            VALUES ({", ".join(["%s"] * len(cols))})
            RETURNING {meta['pk']}
            """,
            vals
        )

        header_id = cur.fetchone()[meta["pk"]]

        # -------- INSERT ITEMS --------
        for item in items:
            item[meta["fk_field"]] = header_id

            cols = list(item.keys())
            vals = list(item.values())

            cur.execute(
                f"""
                INSERT INTO {meta['item_table']} ({", ".join(cols)})
                VALUES ({", ".join(["%s"] * len(cols))})
                """,
                vals
            )

        conn.commit()

    return {"id": header_id}


# -----------------------------
# GET TRANSACTION
# -----------------------------
@router.get("/{entity}")
def list_entities(
    entity: str,
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
):
    """
    List records for any entity

    Example:
    GET /entity/invoice?limit=50&offset=0
    """
    meta = resolve_tables(entity)

    table = meta["header_table"]  # or swap for items if needed

    with get_conn() as conn, conn.cursor() as cur:

        cur.execute(
            f"""
            SELECT *
            FROM {table}
            ORDER BY id DESC
            LIMIT %s OFFSET %s
            """,
            (limit, offset)
        )

        rows = cur.fetchall()

        # optional: total count for pagination UI
        cur.execute(f"SELECT COUNT(*) AS count FROM {table}")
        total = cur.fetchone()["count"]

    return {
        "data": rows,
        "limit": limit,
        "offset": offset,
        "total": total
    }

@router.get("/{entity}/{id}")
def get_transaction(entity: str, id: int):
    """
    Get transaction (header + items)

    Example:
    GET /txn/invoice/1
    """
    meta = resolve_tables(entity)

    with get_conn() as conn, conn.cursor() as cur:

        cur.execute(
            f"""
            SELECT * FROM {meta['header_table']}
            WHERE {meta['pk']} = %s
            """,
            (id,)
        )

        header = cur.fetchone()
        if not header:
            raise HTTPException(404, "Transaction not found")

        cur.execute(
            f"""
            SELECT * FROM {meta['item_table']}
            WHERE {meta['fk_field']} = %s
            """,
            (id,)
        )

        items = cur.fetchall()

    return {
        "header": header,
        "items": items
    }


# -----------------------------
# UPDATE TRANSACTION
# -----------------------------
@router.put("/{entity}/{id}")
def update_transaction(entity: str, id: int, payload: dict = Body(...)):
    """
    Update transaction (full replace of header + items)

    ```json
    {
      "header": {
        "invoice_no": "INV-1001",
        "vendor": "Apple India Pvt Ltd",
        "date": "2026-04-11",
        "status": "Submitted"
      },
      "items": [
        {
          "item": "MacBook Pro",
          "qty": 1,
          "price": 2500,
          "total": 2500
        }
      ]
    }
    ```
    """
    meta = resolve_tables(entity)

    header = payload.get("header", {})
    items = payload.get("items", [])

    if not header:
        raise HTTPException(400, "Header is required")

    with get_conn() as conn, conn.cursor() as cur:

        # -------- UPDATE HEADER --------
        set_clause = ", ".join([f"{k}=%s" for k in header.keys()])

        cur.execute(
            f"""
            UPDATE {meta['header_table']}
            SET {set_clause}
            WHERE {meta['pk']} = %s
            """,
            list(header.values()) + [id]
        )

        # -------- DELETE OLD ITEMS --------
        cur.execute(
            f"""
            DELETE FROM {meta['item_table']}
            WHERE {meta['fk_field']} = %s
            """,
            (id,)
        )

        # -------- INSERT NEW ITEMS --------
        for item in items:
            item[meta["fk_field"]] = id

            cols = list(item.keys())
            vals = list(item.values())

            cur.execute(
                f"""
                INSERT INTO {meta['item_table']} ({", ".join(cols)})
                VALUES ({", ".join(["%s"] * len(cols))})
                """,
                vals
            )

        conn.commit()

    return {"status": "updated", "id": id}


# -----------------------------
# DELETE TRANSACTION
# -----------------------------
@router.delete("/{entity}/{id}")
def delete_transaction(entity: str, id: int):
    """
    Delete transaction

    Example:
    DELETE /txn/invoice/1
    """
    meta = resolve_tables(entity)

    with get_conn() as conn, conn.cursor() as cur:

        cur.execute(
            f"""
            DELETE FROM {meta['item_table']}
            WHERE {meta['fk_field']} = %s
            """,
            (id,)
        )

        cur.execute(
            f"""
            DELETE FROM {meta['header_table']}
            WHERE {meta['pk']} = %s
            """,
            (id,)
        )

        conn.commit()

    return {"status": "deleted", "id": id}