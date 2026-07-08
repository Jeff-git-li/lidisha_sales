from __future__ import annotations

from dataclasses import asdict
from typing import Any

from assets.asset_service import get_product_image
from queries.dashboard import get_dashboard_kpis
from queries.filters import build_where_clause, normalize_filter_values
from queries.products import get_product_explorer, get_product_explorer_options
from queries.retail_queries import JOINED_CTE, _query_all, _query_one, get_category_ranking, get_hot_matrix
from queries.regions import REGION_GROUPS, expand_region_values, get_region_options


YEAR_PREFIX_MAP = {
    "KP": 2025,
    "KU": 2026,
}

SEASON_CODE_MAP = {
    "1": "春季",
    "2": "夏季",
    "3": "秋季",
    "4": "冬季",
}


def _normalize_home_filters(filters: dict[str, Any] | None) -> dict[str, Any]:
    normalized = normalize_filter_values(filters)
    query_filters: dict[str, Any] = {}

    for key in ("start_date", "end_date", "wave", "source_file"):
        values = normalized.get(key, [])
        if values:
            query_filters[key] = values

    if normalized.get("region"):
        expanded_regions = expand_region_values(normalized.get("region", []))
        if expanded_regions:
            query_filters["region_name"] = expanded_regions
    if normalized.get("category"):
        query_filters["big_category_name"] = normalized.get("category", [])
    if normalized.get("store"):
        query_filters["store_name"] = normalized.get("store", [])
    if normalized.get("year_prefix"):
        years = [str(YEAR_PREFIX_MAP.get(prefix, "")) for prefix in normalized.get("year_prefix", []) if YEAR_PREFIX_MAP.get(prefix)]
        if years:
            query_filters["year"] = years
    if normalized.get("season_code"):
        seasons = [SEASON_CODE_MAP.get(code, "") for code in normalized.get("season_code", []) if SEASON_CODE_MAP.get(code)]
        if seasons:
            query_filters["season_name"] = seasons

    return query_filters


def get_home_options() -> dict[str, list[dict[str, str]]]:
    options = get_product_explorer_options()
    options["region_options"] = get_region_options()
    return options


def _attach_image_urls(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for row in rows:
        image = get_product_image(str(row.get("product_code", "") or ""), row.get("color_code"))
        row["image_url"] = image.get("image_url", "")
    return rows


def get_home_sales_rows(filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    query_filters = _normalize_home_filters(filters)
    where_sql, params = build_where_clause(query_filters, core_only=True)
    sql = f"""
    {JOINED_CTE}
    SELECT
        product_code AS 商品代码,
        color_code AS 颜色代码,
        MAX(product_name) AS 商品名称,
        MAX(color_name) AS 颜色名称,
        MAX(category_name) AS 品类,
        MAX(big_category_name) AS 大类,
        MAX(year) AS 年份,
        MAX(season_name) AS 季节,
        MAX(wave) AS 波段,
        MAX(designer_name) AS 设计师,
        MAX(standard_price) AS 选定价,
        COALESCE(SUM(qty), 0) AS 销量,
        COALESCE(SUM(effective_amount), 0) AS 销售额,
        COUNT(*) AS sales_rows
    FROM joined
    {where_sql}
    GROUP BY product_code, color_code
    ORDER BY 销售额 DESC, 销量 DESC, product_code, color_code
    """
    rows = _query_all(sql, params)
    for index, row in enumerate(rows, start=1):
        row["排名"] = index
        row["销量"] = int(round(row.get("销量", 0) or 0))
        row["销售额"] = round(float(row.get("销售额", 0) or 0), 2)
    return _attach_image_urls(rows)


def get_home_dashboard(filters: dict[str, Any] | None = None, top_n: int = 20) -> dict[str, Any]:
    query_filters = _normalize_home_filters(filters)
    home_options = get_home_options()
    normalized_filters = normalize_filter_values(filters)
    where_sql, params = build_where_clause(query_filters, core_only=True)
    dashboard_summary = get_dashboard_kpis(query_filters)

    summary_sql = f"""
    {JOINED_CTE}
    SELECT
        COALESCE(MAX(sale_date), '') AS max_sale_date,
        COALESCE(MIN(sale_date), '') AS min_sale_date
    FROM joined
    {where_sql}
    """
    summary_row = _query_one(summary_sql, params)

    top_products, _ = get_product_explorer(query_filters, sort="sales_amount", order="desc", page=1, per_page=int(top_n))
    top_products_rows = [
        {
            **asdict(item),
            "排名": index,
            "销量": int(round(getattr(item, "sales_qty", 0) or getattr(item, "qty", 0) or 0)),
            "销售额": round(float(getattr(item, "sales_amount", 0) or getattr(item, "amount", 0) or 0), 2),
        }
        for index, item in enumerate(top_products, start=1)
    ]
    top_products_rows = _attach_image_urls(top_products_rows)

    region_sql = f"""
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
    ORDER BY total_amount DESC, total_qty DESC, region_name
    """
    region_rows = _query_all(region_sql, params)
    for index, row in enumerate(region_rows, start=1):
        row["排名"] = index
        row["区域名称"] = row.get("region_name", "")
        row["销量"] = int(round(row.get("total_qty", 0) or 0))
        row["销售额"] = round(float(row.get("total_amount", 0) or 0), 2)

    by_category_rows = get_category_ranking(query_filters, top_n=9999)
    by_category = []
    for row in by_category_rows:
        by_category.append({"品类": row.get("category_name", ""), "销量": int(round(row.get("total_qty", 0) or 0)), "销售额": round(float(row.get("total_amount", 0) or 0), 2)})

    by_store_sql = f"""
    {JOINED_CTE}
    SELECT
        COALESCE(store_name, store_code) AS store_name,
        COALESCE(SUM(qty), 0) AS total_qty,
        COALESCE(SUM(effective_amount), 0) AS total_amount
    FROM joined
    {where_sql}
    GROUP BY COALESCE(store_name, store_code)
    ORDER BY total_qty DESC, total_amount DESC, store_name
    LIMIT ?
    """
    by_store = _query_all(by_store_sql, params + [int(top_n)])
    for row in by_store:
        row["商店名称"] = row.get("store_name", "")
        row["销量"] = int(round(row.get("total_qty", 0) or 0))
        row["销售额"] = round(float(row.get("total_amount", 0) or 0), 2)

    daily_sales_sql = f"""
    {JOINED_CTE}
    SELECT
        sale_date,
        COALESCE(SUM(qty), 0) AS total_qty,
        COALESCE(SUM(effective_amount), 0) AS total_amount
    FROM joined
    {where_sql}
    GROUP BY sale_date
    ORDER BY sale_date
    """
    daily_sales = _query_all(daily_sales_sql, params)
    for row in daily_sales:
        row["日期"] = str(row.get("sale_date", "") or "")
        row["销量"] = int(round(row.get("total_qty", 0) or 0))
        row["销售额"] = round(float(row.get("total_amount", 0) or 0), 2)

    matrix_rows = get_hot_matrix(query_filters, top_n=min(int(top_n), 30))
    matrix = _attach_image_urls(matrix_rows)

    region_top: dict[str, list[dict[str, Any]]] = {}
    for name, members in REGION_GROUPS.items():
        if name == "全国":
            region_top[name] = [dict(row) for row in top_products_rows]
            continue
        member_filters = dict(query_filters)
        if members:
            member_filters["region_name"] = members
        member_rows, _ = get_product_explorer(member_filters, sort="sales_amount", order="desc", page=1, per_page=int(top_n))
        region_top[name] = _attach_image_urls([
            {
                **asdict(item),
                "排名": index,
                "销量": int(round(getattr(item, "sales_qty", 0) or getattr(item, "qty", 0) or 0)),
                "销售额": round(float(getattr(item, "sales_amount", 0) or getattr(item, "amount", 0) or 0), 2),
            }
            for index, item in enumerate(member_rows, start=1)
        ])

    global_top = [dict(row) for row in top_products_rows]
    color_top_sql = f"""
    {JOINED_CTE}
    SELECT
        product_code,
        color_code,
        MAX(product_name) AS product_name,
        MAX(color_name) AS color_name,
        MAX(year) AS year,
        MAX(season_name) AS season_name,
        MAX(wave) AS wave,
        MAX(category_name) AS category_name,
        MAX(big_category_name) AS big_category_name,
        MAX(designer_name) AS designer_name,
        COALESCE(SUM(qty), 0) AS sales_qty,
        COALESCE(SUM(effective_amount), 0) AS sales_amount,
        COUNT(*) AS sales_rows
    FROM joined
    {where_sql}
    GROUP BY product_code, color_code
    ORDER BY sales_amount DESC, sales_qty DESC, product_code, color_code
    LIMIT ?
    """
    color_top = _query_all(color_top_sql, params + [int(top_n)])
    for index, row in enumerate(color_top, start=1):
        row["排名"] = index
        row["销量"] = int(round(row.get("sales_qty", 0) or 0))
        row["销售额"] = round(float(row.get("sales_amount", 0) or 0), 2)
    color_top = _attach_image_urls(color_top)

    sales_rows = get_home_sales_rows(filters)

    filters_echo = {
        "date_preset": normalized_filters.get("date_preset", ["week"])[0] if normalized_filters.get("date_preset") else "week",
        "start_date": normalized_filters.get("start_date", [""])[0] if normalized_filters.get("start_date") else "",
        "end_date": normalized_filters.get("end_date", [""])[0] if normalized_filters.get("end_date") else "",
        "region": normalized_filters.get("region", ["全国"]) or ["全国"],
        "category": normalized_filters.get("category", []),
        "year_prefix": normalized_filters.get("year_prefix", ["KU"]) or ["KU"],
        "season_code": normalized_filters.get("season_code", ["1"]) or ["1"],
        "wave": normalized_filters.get("wave", []),
        "store": normalized_filters.get("store", []),
        "top_n": [str(top_n)],
    }

    summary = {
        **dashboard_summary,
        "latest_data_date": str(summary_row.get("max_sale_date", "") or ""),
    }
    meta = {
        "date_min": str(summary_row.get("min_sale_date", "") or ""),
        "date_max": str(summary_row.get("max_sale_date", "") or ""),
        "default_year_prefix": "KU",
        "default_season_code": "1",
        "year_options": home_options.get("year_options", []),
        "season_options": home_options.get("season_options", []),
        "wave_options": home_options.get("wave_options", []),
        "region_options": home_options.get("region_options", []),
    }
    return {
        "summary": summary,
        "global_top": global_top,
        "color_top": color_top,
        "region_top": region_top,
        "by_region": region_rows,
        "by_category": by_category,
        "by_store": by_store,
        "daily_sales": [
            {
                "日期": row["日期"],
                "销量": int(row["销量"]),
                "销售额": round(float(row["销售额"]), 2),
            }
            for row in daily_sales
        ],
        "matrix": matrix,
        "sales_rows": sales_rows,
        "filters": filters_echo,
        "meta": meta,
    }
