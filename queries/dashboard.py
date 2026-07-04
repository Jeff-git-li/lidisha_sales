from __future__ import annotations

from typing import Any

from queries.filters import build_where_clause, normalize_filter_values
from queries.retail_queries import JOINED_CTE, _query_one


def _to_query_filters(filters: dict[str, Any] | None) -> dict[str, Any]:
    filters = normalize_filter_values(filters)
    query_filters: dict[str, Any] = {}

    for key in ("start_date", "end_date", "region_name", "channel_code", "category_name", "big_category_name", "year", "season_name", "wave", "designer_name", "product_code", "store_code", "store_name", "store_type_name", "source_file"):
        values = filters.get(key, [])
        if values:
            query_filters[key] = values

    return query_filters


def get_dashboard_kpis(filters: dict[str, Any] | None = None, core_only: bool = True) -> dict[str, Any]:
    query_filters = _to_query_filters(filters)
    where_sql, params = build_where_clause(query_filters, core_only)
    if not query_filters.get("source_file"):
        where_sql += " AND source_file LIKE ?" if where_sql else " WHERE source_file LIKE ?"
        params.append("%零售销售%")
    sql = f"""
    {JOINED_CTE}
    SELECT
        COALESCE(SUM(qty), 0) AS total_qty,
        COALESCE(SUM(effective_amount), 0) AS total_amount,
        COUNT(DISTINCT product_code) AS core_product_count,
        COUNT(DISTINCT store_code) AS store_count,
        CASE
            WHEN COUNT(DISTINCT sale_date) = 0 THEN 0
            ELSE ROUND(COALESCE(SUM(qty), 0) * 1.0 / COUNT(DISTINCT sale_date), 2)
        END AS avg_daily_sales
    FROM joined
    {where_sql}
    """
    row = _query_one(sql, params)
    return {
        "总销量": row.get("total_qty", 0),
        "总销售额": row.get("total_amount", 0),
        "核心款数": row.get("core_product_count", 0),
        "商店数": row.get("store_count", 0),
        "日均销量": row.get("avg_daily_sales", 0),
    }