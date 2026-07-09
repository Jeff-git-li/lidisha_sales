from __future__ import annotations

from typing import Any

from database import get_db_connection


def fetch_all(sql: str, params: list[Any] | tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
    with get_db_connection() as conn:
        rows = conn.execute(sql, params or []).fetchall()
    return [dict(row) for row in rows]


def fetch_one(sql: str, params: list[Any] | tuple[Any, ...] | None = None) -> dict[str, Any]:
    rows = fetch_all(sql, params)
    return rows[0] if rows else {}
