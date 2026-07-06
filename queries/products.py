from __future__ import annotations

from typing import Any

from assets.asset_service import get_product_image
from database import get_db_connection
from queries.filters import build_where_clause, normalize_filter_values
from queries.retail_queries import _query_all
from semantic.product_metrics import ProductPerformance


EXPLORER_PAGE_SIZE = 24
EXPLORER_SORT_FIELDS = {
    "sales_qty": "sales_qty DESC, sales_amount DESC, product_code ASC",
    "sales_amount": "sales_amount DESC, sales_qty DESC, product_code ASC",
    "average_price": "average_unit_price DESC, sales_qty DESC, product_code ASC",
    "store_coverage": "store_coverage DESC, sales_qty DESC, product_code ASC",
    "standard_price": "standard_price DESC, sales_qty DESC, product_code ASC",
    "newest": "year DESC, season_sort DESC, wave_sort DESC, product_code ASC",
}


def _normalize_sort(sort: str | None) -> str:
    value = str(sort or "sales_qty").strip().lower()
    return value if value in EXPLORER_SORT_FIELDS else "sales_qty"


def _normalize_order(order: str | None) -> str:
    value = str(order or "desc").strip().lower()
    return "asc" if value == "asc" else "desc"


def _price_band_sql(column_name: str = "p.standard_retail_price") -> str:
    return """
        CASE
            WHEN {column_name} IS NULL OR {column_name} <= 0 THEN '未知'
            WHEN {column_name} < 200 THEN '0-199'
            WHEN {column_name} < 400 THEN '200-399'
            WHEN {column_name} < 600 THEN '400-599'
            WHEN {column_name} < 800 THEN '600-799'
            ELSE '800+'
        END
    """.format(column_name=column_name)


def _season_sort_sql() -> str:
    return """
        CASE p.season_name
            WHEN '春季' THEN 1
            WHEN '夏季' THEN 2
            WHEN '秋季' THEN 3
            WHEN '冬季' THEN 4
            ELSE 0
        END
    """


def _wave_sort_sql() -> str:
    return """
        CASE
            WHEN p.launch_wave_name IS NULL OR p.launch_wave_name = '' THEN 0
            ELSE COALESCE(CAST(REPLACE(REPLACE(p.launch_wave_name, '第', ''), '波', '') AS INTEGER), 0)
        END
    """


def _translate_filters(filters: dict[str, Any] | None) -> dict[str, Any]:
    normalized = normalize_filter_values(filters)
    query_filters: dict[str, Any] = {}

    for key in (
        "start_date",
        "end_date",
        "search",
        "region_name",
        "channel_code",
        "brand_name",
        "category_name",
        "big_category_name",
        "series_name",
        "year",
        "season_name",
        "wave",
        "designer_name",
        "product_code",
        "color_name",
        "price_band",
        "store_code",
        "store_name",
        "store_type_name",
        "source_file",
    ):
        values = normalized.get(key, [])
        if values:
            query_filters[key] = values

    return query_filters


def _build_product_explorer_cte(filters: dict[str, Any] | None = None) -> tuple[str, list[Any]]:
    query_filters = _translate_filters(filters)
    where_sql, params = build_where_clause(query_filters, core_only=True)
    sql = f"""
    WITH joined AS (
        SELECT
            f.product_code,
            f.store_code,
            f.color_name,
            f.sale_date,
            f.date_key,
            f.qty,
            f.amount,
            f.unit_price,
            f.size_name,
            p.product_name,
            p.image_path,
            p.year_code AS year,
            p.year_code AS year_code,
            p.season_name,
            p.season_code,
            p.launch_wave_name AS wave,
            p.brand_name,
            p.designer_name,
            p.category_name,
            p.major_category_name AS big_category_name,
            p.series_name,
            p.standard_retail_price AS standard_price,
            s.region_name,
            s.channel_code,
            s.store_type_name,
            c.year AS calendar_year,
            c.month AS calendar_month,
            c.day AS calendar_day,
            {_price_band_sql()} AS price_band,
            {_season_sort_sql()} AS season_sort,
            {_wave_sort_sql()} AS wave_sort,
            COALESCE(
                NULLIF(f.amount, 0),
                CASE WHEN f.unit_price IS NOT NULL AND f.unit_price != 0 THEN f.qty * f.unit_price ELSE 0 END
            ) AS effective_amount
        FROM fact_retail_sales f
        LEFT JOIN dim_product p ON f.product_code = p.product_code
        LEFT JOIN dim_store s ON f.store_code = s.store_code
        LEFT JOIN dim_calendar c ON f.date_key = c.date_key
    ), aggregated AS (
        SELECT
            product_code,
            MAX(product_name) AS product_name,
            MAX(image_path) AS image_path,
            MAX(year) AS year,
            MAX(season_name) AS season_name,
            MAX(wave) AS wave,
            MAX(brand_name) AS brand_name,
            MAX(designer_name) AS designer_name,
            MAX(category_name) AS category_name,
            MAX(big_category_name) AS big_category_name,
            MAX(series_name) AS series_name,
            MAX(price_band) AS price_band,
            MAX(standard_price) AS standard_price,
            MAX(season_sort) AS season_sort,
            MAX(wave_sort) AS wave_sort,
            COALESCE(SUM(qty), 0) AS sales_qty,
            COALESCE(SUM(effective_amount), 0) AS sales_amount,
            COUNT(DISTINCT store_code) AS store_coverage,
            COUNT(DISTINCT COALESCE(NULLIF(color_name, ''), product_code)) AS color_count,
            COUNT(DISTINCT COALESCE(NULLIF(size_name, ''), product_code)) AS size_count,
            CASE WHEN COALESCE(SUM(qty), 0) = 0 THEN 0 ELSE COALESCE(SUM(effective_amount), 0) / COALESCE(SUM(qty), 1) END AS average_unit_price
        FROM joined
        {where_sql}
        GROUP BY product_code
    )
    """
    return sql, params


def get_product_explorer(
    filters: dict[str, Any] | None = None,
    sort: str | None = None,
    order: str | None = None,
    page: int = 1,
    per_page: int = EXPLORER_PAGE_SIZE,
) -> tuple[list[ProductPerformance], int]:
    base_sql, params = _build_product_explorer_cte(filters)
    sort_key = _normalize_sort(sort)
    sort_order = _normalize_order(order)
    order_sql = EXPLORER_SORT_FIELDS[sort_key]
    if sort_order == "asc":
        order_sql = ", ".join(
            part.replace(" DESC", " ASC") if " DESC" in part else part.replace(" ASC", " DESC")
            for part in order_sql.split(", ")
        )

    offset = max(0, (int(page) - 1) * int(per_page))

    count_sql = f"""
    {base_sql}
    SELECT COUNT(*) AS total_count
    FROM aggregated
    """
    total_count = int(_query_all(count_sql, params)[0]["total_count"] or 0)

    data_sql = f"""
    {base_sql}
    SELECT
        *,
        COUNT(*) OVER() AS total_count
    FROM aggregated
    ORDER BY {order_sql}
    LIMIT ? OFFSET ?
    """
    rows = _query_all(data_sql, params + [int(per_page), int(offset)])
    products: list[ProductPerformance] = []
    for row in rows:
        data = dict(row)
        data["qty"] = data.get("sales_qty", 0)
        data["amount"] = data.get("sales_amount", 0)
        data["store_count"] = data.get("store_coverage", 0)
        asset = get_product_image(data.get("product_code", ""))
        data.update(asset)
        products.append(ProductPerformance.from_query_row(data))
    return products, total_count


def get_product_explorer_options() -> dict[str, list[dict[str, str]]]:
    sql_templates = {
        "year_options": "SELECT DISTINCT COALESCE(NULLIF(TRIM(year_code), ''), '') AS value FROM dim_product WHERE COALESCE(NULLIF(TRIM(year_code), ''), '') <> '' ORDER BY value DESC",
        "season_options": "SELECT DISTINCT COALESCE(NULLIF(TRIM(season_name), ''), '') AS value FROM dim_product WHERE COALESCE(NULLIF(TRIM(season_name), ''), '') <> '' ORDER BY CASE value WHEN '春季' THEN 1 WHEN '夏季' THEN 2 WHEN '秋季' THEN 3 WHEN '冬季' THEN 4 ELSE 99 END",
        "wave_options": "SELECT DISTINCT COALESCE(NULLIF(TRIM(launch_wave_name), ''), '') AS value FROM dim_product WHERE COALESCE(NULLIF(TRIM(launch_wave_name), ''), '') <> '' ORDER BY value",
        "brand_options": "SELECT DISTINCT COALESCE(NULLIF(TRIM(brand_name), ''), '') AS value FROM dim_product WHERE COALESCE(NULLIF(TRIM(brand_name), ''), '') <> '' ORDER BY value",
        "designer_options": "SELECT DISTINCT COALESCE(NULLIF(TRIM(designer_name), ''), '') AS value FROM dim_product WHERE COALESCE(NULLIF(TRIM(designer_name), ''), '') <> '' ORDER BY value",
        "category_options": "SELECT DISTINCT COALESCE(NULLIF(TRIM(category_name), ''), '') AS value FROM dim_product WHERE COALESCE(NULLIF(TRIM(category_name), ''), '') <> '' ORDER BY value",
        "big_category_options": "SELECT DISTINCT COALESCE(NULLIF(TRIM(major_category_name), ''), '') AS value FROM dim_product WHERE COALESCE(NULLIF(TRIM(major_category_name), ''), '') <> '' ORDER BY value",
        "series_options": "SELECT DISTINCT COALESCE(NULLIF(TRIM(series_name), ''), '') AS value FROM dim_product WHERE COALESCE(NULLIF(TRIM(series_name), ''), '') <> '' ORDER BY value",
        "price_band_options": f"SELECT DISTINCT price_band AS value FROM (SELECT {_price_band_sql('standard_retail_price')} AS price_band FROM dim_product) WHERE COALESCE(NULLIF(TRIM(price_band), ''), '') <> '' ORDER BY CASE price_band WHEN '未知' THEN 99 WHEN '0-199' THEN 1 WHEN '200-399' THEN 2 WHEN '400-599' THEN 3 WHEN '600-799' THEN 4 ELSE 5 END",
        "color_options": "SELECT DISTINCT COALESCE(NULLIF(TRIM(color_name), ''), '') AS value FROM fact_retail_sales WHERE COALESCE(NULLIF(TRIM(color_name), ''), '') <> '' ORDER BY value",
        "store_options": "SELECT DISTINCT COALESCE(NULLIF(TRIM(store_name), ''), '') AS value FROM dim_store WHERE COALESCE(NULLIF(TRIM(store_name), ''), '') <> '' ORDER BY value",
    }

    options: dict[str, list[dict[str, str]]] = {}
    with get_db_connection() as conn:
        for option_key, sql in sql_templates.items():
            rows = conn.execute(sql).fetchall()
            options[option_key] = [{"value": str(row["value"]), "label": str(row["value"])} for row in rows]
    return options