from __future__ import annotations

from typing import Any

from dashboard.cache import fetch_all, fetch_one
from queries.filters import normalize_filter_values


def _normalized(filters: dict[str, Any] | None) -> dict[str, list[str]]:
    return normalize_filter_values(filters)


def get_snapshot_summary(filters: dict[str, Any] | None = None) -> dict[str, Any]:
    normalized = _normalized(filters)
    snapshot_date = normalized.get("snapshot_date", [""])[0] if normalized.get("snapshot_date") else ""
    if snapshot_date:
        row = fetch_one(
            """
            SELECT *
            FROM dashboard_snapshot
            WHERE snapshot_date = ?
            """,
            [snapshot_date],
        )
        if row:
            return row
    return fetch_one(
        """
        SELECT *
        FROM dashboard_snapshot
        ORDER BY snapshot_date DESC
        LIMIT 1
        """
    )


def get_snapshot_top_products(filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    normalized = _normalized(filters)
    snapshot_date = normalized.get("snapshot_date", [""])[0] if normalized.get("snapshot_date") else ""
    if snapshot_date:
        rows = fetch_all(
            """
            SELECT *
            FROM dashboard_top_products
            WHERE snapshot_date = ?
            ORDER BY rank ASC, sales_amount DESC, sales_qty DESC, product_code ASC, color_code ASC
            """,
            [snapshot_date],
        )
        if rows:
            return rows
    return fetch_all(
        """
        SELECT *
        FROM dashboard_top_products
        ORDER BY snapshot_date DESC, rank ASC, sales_amount DESC, sales_qty DESC, product_code ASC, color_code ASC
        LIMIT 5
        """
    )


def get_snapshot_regions(filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    normalized = _normalized(filters)
    snapshot_date = normalized.get("snapshot_date", [""])[0] if normalized.get("snapshot_date") else ""
    if snapshot_date:
        rows = fetch_all(
            """
            SELECT *
            FROM dashboard_regions
            WHERE snapshot_date = ?
            ORDER BY rank ASC, total_amount DESC, total_qty DESC, region_name ASC
            LIMIT 4
            """,
            [snapshot_date],
        )
        if rows:
            return rows
    return fetch_all(
        """
        SELECT *
        FROM dashboard_regions
        ORDER BY snapshot_date DESC, rank ASC, total_amount DESC, total_qty DESC, region_name ASC
        LIMIT 4
        """
    )


def get_snapshot_alerts() -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT *
        FROM dashboard_alerts
        ORDER BY snapshot_date DESC, alert_order ASC
        """
    )


def get_snapshot_sales_rows(filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    normalized = _normalized(filters)
    snapshot_date = normalized.get("snapshot_date", [""])[0] if normalized.get("snapshot_date") else ""
    if snapshot_date:
        rows = fetch_all(
            """
            SELECT *
            FROM dashboard_sales_rows
            WHERE snapshot_date = ?
            ORDER BY sales_amount DESC, sales_qty DESC, product_code ASC, color_code ASC
            """,
            [snapshot_date],
        )
        if rows:
            return rows
    return fetch_all(
        """
        SELECT *
        FROM dashboard_sales_rows
        ORDER BY snapshot_date DESC, sales_amount DESC, sales_qty DESC, product_code ASC, color_code ASC
        LIMIT 500
        """
    )


def get_snapshot_daily_sales(snapshot_date: str | None = None) -> list[dict[str, Any]]:
    if snapshot_date:
        rows = fetch_all(
            """
            SELECT *
            FROM dashboard_daily_sales
            WHERE snapshot_date = ?
            ORDER BY sale_date ASC
            """,
            [snapshot_date],
        )
        if rows:
            return rows
    return fetch_all(
        """
        SELECT *
        FROM dashboard_daily_sales
        ORDER BY snapshot_date DESC, sale_date ASC
        LIMIT 31
        """
    )


def get_snapshot_categories(snapshot_date: str | None = None) -> list[dict[str, Any]]:
    if snapshot_date:
        rows = fetch_all(
            """
            SELECT *
            FROM dashboard_category_summary
            WHERE snapshot_date = ?
            ORDER BY rank ASC
            """,
            [snapshot_date],
        )
        if rows:
            return rows
    return fetch_all(
        """
        SELECT *
        FROM dashboard_category_summary
        ORDER BY snapshot_date DESC, rank ASC
        LIMIT 20
        """
    )


def get_snapshot_stores(snapshot_date: str | None = None) -> list[dict[str, Any]]:
    if snapshot_date:
        rows = fetch_all(
            """
            SELECT *
            FROM dashboard_store_summary
            WHERE snapshot_date = ?
            ORDER BY rank ASC
            """,
            [snapshot_date],
        )
        if rows:
            return rows
    return fetch_all(
        """
        SELECT *
        FROM dashboard_store_summary
        ORDER BY snapshot_date DESC, rank ASC
        LIMIT 20
        """
    )


def get_snapshot_region_top(snapshot_date: str | None = None) -> dict[str, list[dict[str, Any]]]:
    order = ["全国", "北区", "中区", "南区"]
    result: dict[str, list[dict[str, Any]]] = {}
    for region_name in order:
        if snapshot_date:
            rows = fetch_all(
                """
                SELECT *
                FROM dashboard_region_top_products
                WHERE snapshot_date = ? AND region_name = ?
                ORDER BY rank ASC
                LIMIT 20
                """,
                [snapshot_date, region_name],
            )
        else:
            rows = fetch_all(
                """
                SELECT *
                FROM dashboard_region_top_products
                WHERE region_name = ?
                ORDER BY snapshot_date DESC, rank ASC
                LIMIT 20
                """,
                [region_name],
            )
        result[region_name] = rows
    return result


def get_snapshot_matrix(snapshot_date: str | None = None) -> list[dict[str, Any]]:
    if snapshot_date:
        rows = fetch_all(
            """
            SELECT *
            FROM dashboard_matrix
            WHERE snapshot_date = ?
            ORDER BY rank ASC
            """,
            [snapshot_date],
        )
        if rows:
            return rows
    return fetch_all(
        """
        SELECT *
        FROM dashboard_matrix
        ORDER BY snapshot_date DESC, rank ASC
        LIMIT 30
        """
    )
