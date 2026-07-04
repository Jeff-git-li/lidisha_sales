from __future__ import annotations

from typing import Any

from queries.filters import build_where_clause, normalize_filter_values
from queries.retail_queries import JOINED_CTE, _query_one


REGION_GROUPS = {
    "全国": [],
    "北区": ["华北", "东北", "西北"],
    "中区": ["华中", "西南", "华东", "河南"],
    "南区": ["华南"],
}

YEAR_PREFIX_MAP = {
    "KP": "2025",
    "KU": "2026",
}
def _expand_region_values(values: list[str]) -> list[str]:
    selected = [value for value in values if value and value != "全国"]
    if not selected:
        return []

    expanded: list[str] = []
    for value in selected:
        members = REGION_GROUPS.get(value)
        if members:
            expanded.extend(members)
        else:
            expanded.append(value)
    return list(dict.fromkeys(expanded))


def _to_query_filters(filters: dict[str, Any] | None) -> dict[str, Any]:
    filters = normalize_filter_values(filters)
    query_filters: dict[str, Any] = {}

    start_date = filters.get("start_date", [])
    if start_date:
        query_filters["start_date"] = start_date[0]

    end_date = filters.get("end_date", [])
    if end_date:
        query_filters["end_date"] = end_date[0]

    region_values = filters.get("region", []) or filters.get("region_name", [])
    expanded_regions = _expand_region_values(region_values)
    if expanded_regions:
        query_filters["region_name"] = expanded_regions

    category_values = filters.get("category", []) or filters.get("big_category_name", [])
    if category_values:
        query_filters["big_category_name"] = category_values

    store_values = filters.get("store", []) or filters.get("store_name", []) or filters.get("store_code", [])
    if store_values:
        query_filters["store_name"] = store_values

    year_values = filters.get("year_prefix", []) or filters.get("year_code", []) or filters.get("year", [])
    if year_values:
        mapped_years: list[str] = []
        for value in year_values:
            mapped_years.append(YEAR_PREFIX_MAP.get(value, value))
        query_filters["year_code"] = mapped_years

    season_values = filters.get("season_code", []) or filters.get("season_name", [])
    if season_values:
        query_filters["season_code"] = season_values

    wave_values = filters.get("wave", [])
    if wave_values:
        query_filters["wave"] = wave_values

    product_values = filters.get("product_code", [])
    if product_values:
        query_filters["product_code"] = product_values

    source_values = filters.get("source_file", [])
    if source_values:
        query_filters["source_file"] = source_values

    return query_filters


def get_dashboard_kpis(filters: dict[str, Any] | None = None, core_only: bool = True) -> dict[str, Any]:
    query_filters = _to_query_filters(filters)
    where_sql, params = build_where_clause(query_filters, core_only)
    product_clause = " AND product_code LIKE 'K%' AND COALESCE(SUBSTR(product_code, 5, 1), '') NOT IN ('P', 'S')"
    if not query_filters.get("source_file"):
        where_sql += " AND source_file LIKE ?" if where_sql else " WHERE source_file LIKE ?"
        params.append("%零售销售%")
    where_sql += product_clause if where_sql else f" WHERE 1=1{product_clause}"
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