from __future__ import annotations

from typing import Any

from queries.filters import build_where_clause, normalize_filter_values
from queries.retail_queries import _query_all


def _translate_filters(filters: dict[str, Any] | None) -> dict[str, Any]:
    normalized = normalize_filter_values(filters)
    query_filters: dict[str, Any] = {}

    for key in ("start_date", "end_date", "region_name", "channel_code", "category_name", "big_category_name", "year", "season_name", "wave", "designer_name", "product_code", "store_code", "store_name", "store_type_name", "source_file"):
        values = normalized.get(key, [])
        if values:
            query_filters[key] = values

    return query_filters


def get_top20_products(filters: dict[str, Any] | None = None, top_n: int = 20) -> list[dict[str, Any]]:
    query_filters = _translate_filters(filters)
    where_sql, params = build_where_clause(query_filters, core_only=True)
    sql = f"""
    WITH joined AS (
        SELECT
            f.product_code,
            f.store_code,
            f.sale_date,
            f.date_key,
            f.qty,
            f.amount,
            f.unit_price,
            f.color_name,
            f.size_name,
            p.product_name,
            p.image_path,
            p.year_code AS year,
            p.year_code AS year_code,
            p.season_name,
            p.season_code,
            p.launch_wave_name AS wave,
            p.designer_name,
            p.category_name,
            p.major_category_name AS big_category_name,
            p.standard_retail_price AS standard_price,
            s.region_name,
            s.channel_code,
            s.store_type_name,
            c.year AS calendar_year,
            c.month AS calendar_month,
            c.day AS calendar_day,
            COALESCE(
                NULLIF(f.amount, 0),
                CASE WHEN f.unit_price IS NOT NULL AND f.unit_price != 0 THEN f.qty * f.unit_price ELSE 0 END
            ) AS effective_amount
        FROM fact_retail_sales f
        LEFT JOIN dim_product p ON f.product_code = p.product_code
        LEFT JOIN dim_store s ON f.store_code = s.store_code
        LEFT JOIN dim_calendar c ON f.date_key = c.date_key
    )
    SELECT
        product_code,
        MAX(product_name) AS product_name,
        MAX(image_path) AS image_path,
        MAX(year) AS year,
        MAX(season_name) AS season_name,
        MAX(wave) AS wave,
        MAX(designer_name) AS designer_name,
        MAX(category_name) AS category_name,
        MAX(big_category_name) AS big_category_name,
        MAX(standard_price) AS standard_price,
        COALESCE(SUM(qty), 0) AS qty,
        COALESCE(SUM(effective_amount), 0) AS amount,
        COUNT(DISTINCT store_code) AS store_count,
        COUNT(DISTINCT COALESCE(NULLIF(color_name, ''), product_code)) AS color_count,
        COUNT(DISTINCT COALESCE(NULLIF(size_name, ''), product_code)) AS size_count
    FROM joined
    {where_sql}
    GROUP BY product_code
    ORDER BY qty DESC, amount DESC, product_code
    LIMIT ?
    """
    rows = _query_all(sql, params + [int(top_n)])
    return [dict(row) for row in rows]
