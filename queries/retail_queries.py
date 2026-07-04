from __future__ import annotations

from typing import Any

from database import get_db_connection
from queries.filters import build_dimension_joins, build_where_clause


JOINED_CTE = f"""
WITH joined AS (
    SELECT
        f.id,
        f.sale_date,
        f.date_key,
        f.product_code,
        f.store_code,
        s.store_name,
        f.color_name,
        f.size_name,
        f.qty,
        f.amount,
        f.unit_price,
        f.discount_rate,
        f.source_file,
        f.source_row_hash,
        f.load_batch_id,
        f.import_run_time,
        f.imported_at,
        p.product_name,
        p.year_code AS year,
        p.year_code AS year_code,
        p.season_code,
        p.season_name,
        p.launch_wave_name AS wave,
        p.category_name,
        p.major_category_name AS big_category_name,
        p.designer_name,
        s.region_name,
        s.channel_code,
        s.store_type_name,
        c.year AS calendar_year,
        c.month AS calendar_month,
        c.day AS calendar_day,
        COALESCE(
            NULLIF(f.amount, 0),
            CASE
                WHEN f.unit_price IS NOT NULL AND f.unit_price != 0 THEN f.qty * f.unit_price
                ELSE 0
            END
        ) AS effective_amount
    FROM fact_retail_sales f
    {build_dimension_joins()}
)
"""


def _query_all(sql: str, params: list[Any] | tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
    with get_db_connection() as conn:
        rows = conn.execute(sql, params or []).fetchall()
    return [dict(row) for row in rows]


def _query_one(sql: str, params: list[Any] | tuple[Any, ...] | None = None) -> dict[str, Any]:
    rows = _query_all(sql, params)
    return rows[0] if rows else {}


def get_sales_summary(filters: dict[str, Any] | None = None, core_only: bool = True) -> dict[str, Any]:
    where_sql, params = build_where_clause(filters, core_only)
    sql = f"""
    {JOINED_CTE}
    SELECT
        COUNT(*) AS rows,
        COALESCE(SUM(qty), 0) AS total_qty,
        COALESCE(SUM(effective_amount), 0) AS total_amount,
        COUNT(DISTINCT product_code) AS product_count,
        COUNT(DISTINCT store_code) AS store_count,
        COUNT(DISTINCT region_name) AS region_count,
        COUNT(DISTINCT category_name) AS category_count,
        MIN(sale_date) AS min_sale_date,
        MAX(sale_date) AS max_sale_date
    FROM joined
    {where_sql}
    """
    return _query_one(sql, params)


def get_top_products(filters: dict[str, Any] | None = None, top_n: int = 20, core_only: bool = True) -> list[dict[str, Any]]:
    where_sql, params = build_where_clause(filters, core_only)
    sql = f"""
    {JOINED_CTE}
    SELECT
        product_code,
        MAX(product_name) AS product_name,
        MAX(year) AS year,
        MAX(season_name) AS season_name,
        MAX(wave) AS wave,
        MAX(category_name) AS category_name,
        MAX(big_category_name) AS big_category_name,
        MAX(designer_name) AS designer_name,
        COALESCE(SUM(qty), 0) AS total_qty,
        COALESCE(SUM(effective_amount), 0) AS total_amount,
        COUNT(*) AS sales_rows
    FROM joined
    {where_sql}
    GROUP BY product_code
    ORDER BY total_qty DESC, total_amount DESC, product_code
    LIMIT ?
    """
    rows = _query_all(sql, params + [int(top_n)])
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
    return rows


def get_top_product_colors(filters: dict[str, Any] | None = None, top_n: int = 20, core_only: bool = True) -> list[dict[str, Any]]:
    where_sql, params = build_where_clause(filters, core_only)
    sql = f"""
    {JOINED_CTE}
    SELECT
        product_code,
        MAX(product_name) AS product_name,
        color_name,
        MAX(year) AS year,
        MAX(season_name) AS season_name,
        MAX(wave) AS wave,
        MAX(category_name) AS category_name,
        MAX(big_category_name) AS big_category_name,
        MAX(designer_name) AS designer_name,
        COALESCE(SUM(qty), 0) AS total_qty,
        COALESCE(SUM(effective_amount), 0) AS total_amount,
        COUNT(*) AS sales_rows
    FROM joined
    {where_sql}
    GROUP BY product_code, color_name
    ORDER BY total_qty DESC, total_amount DESC, product_code, color_name
    LIMIT ?
    """
    rows = _query_all(sql, params + [int(top_n)])
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
    return rows


def get_region_ranking(filters: dict[str, Any] | None = None, top_n: int = 20, core_only: bool = True) -> list[dict[str, Any]]:
    where_sql, params = build_where_clause(filters, core_only)
    sql = f"""
    {JOINED_CTE}
    SELECT
        COALESCE(region_name, '未分区') AS region_name,
        COALESCE(SUM(qty), 0) AS total_qty,
        COALESCE(SUM(effective_amount), 0) AS total_amount,
        COUNT(DISTINCT product_code) AS product_count,
        COUNT(DISTINCT store_code) AS store_count
    FROM joined
    {where_sql}
    GROUP BY COALESCE(region_name, '未分区')
    ORDER BY total_qty DESC, total_amount DESC, region_name
    LIMIT ?
    """
    rows = _query_all(sql, params + [int(top_n)])
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
    return rows


def get_category_ranking(filters: dict[str, Any] | None = None, top_n: int = 20, core_only: bool = True) -> list[dict[str, Any]]:
    where_sql, params = build_where_clause(filters, core_only)
    sql = f"""
    {JOINED_CTE}
    SELECT
        COALESCE(category_name, '未分类') AS category_name,
        COALESCE(big_category_name, '未大类') AS big_category_name,
        COALESCE(SUM(qty), 0) AS total_qty,
        COALESCE(SUM(effective_amount), 0) AS total_amount,
        COUNT(DISTINCT product_code) AS product_count
    FROM joined
    {where_sql}
    GROUP BY COALESCE(category_name, '未分类'), COALESCE(big_category_name, '未大类')
    ORDER BY total_qty DESC, total_amount DESC, category_name, big_category_name
    LIMIT ?
    """
    rows = _query_all(sql, params + [int(top_n)])
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
    return rows


def get_hot_matrix(filters: dict[str, Any] | None = None, top_n: int = 20, core_only: bool = True) -> list[dict[str, Any]]:
    where_sql, params = build_where_clause(filters, core_only)
    sql = f"""
    {JOINED_CTE}
    SELECT
        product_code,
        MAX(product_name) AS product_name,
        MAX(category_name) AS category_name,
        MAX(big_category_name) AS big_category_name,
        MAX(year) AS year,
        MAX(season_name) AS season_name,
        MAX(wave) AS wave,
        COALESCE(SUM(qty), 0) AS total_qty,
        COALESCE(SUM(effective_amount), 0) AS total_amount
    FROM joined
    {where_sql}
    GROUP BY product_code
    ORDER BY total_qty DESC, total_amount DESC, product_code
    LIMIT ?
    """
    top_products = _query_all(sql, params + [int(top_n)])
    if not top_products:
        return []

    product_codes = [row["product_code"] for row in top_products]
    matrix_filters = dict(filters or {})
    matrix_filters["product_code"] = product_codes
    matrix_where_sql, matrix_params = build_where_clause(matrix_filters, core_only)
    matrix_sql = f"""
    {JOINED_CTE}
    SELECT
        product_code,
        MAX(product_name) AS product_name,
        COALESCE(region_name, '未分区') AS region_name,
        COALESCE(SUM(qty), 0) AS total_qty,
        COALESCE(SUM(effective_amount), 0) AS total_amount
    FROM joined
    {matrix_where_sql}
    GROUP BY product_code, COALESCE(region_name, '未分区')
    ORDER BY product_code, total_qty DESC, total_amount DESC, region_name
    """
    region_rows = _query_all(matrix_sql, matrix_params)
    region_names = []
    for row in region_rows:
        region_name = row["region_name"]
        if region_name not in region_names:
            region_names.append(region_name)

    grouped: dict[str, dict[str, Any]] = {}
    for row in top_products:
        grouped[row["product_code"]] = {
            "product_code": row["product_code"],
            "product_name": row["product_name"],
            "category_name": row.get("category_name"),
            "big_category_name": row.get("big_category_name"),
            "year": row.get("year"),
            "season_name": row.get("season_name"),
            "wave": row.get("wave"),
            "total_qty": row.get("total_qty", 0),
            "total_amount": row.get("total_amount", 0),
        }
        for region_name in region_names:
            grouped[row["product_code"]][f"{region_name}_qty"] = 0
            grouped[row["product_code"]][f"{region_name}_amount"] = 0

    for row in region_rows:
        item = grouped.get(row["product_code"])
        if not item:
            continue
        item[f"{row['region_name']}_qty"] = row.get("total_qty", 0)
        item[f"{row['region_name']}_amount"] = row.get("total_amount", 0)

    return [dict(value, rank=index) for index, value in enumerate(grouped.values(), start=1)]
