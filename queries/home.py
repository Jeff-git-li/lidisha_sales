from __future__ import annotations

from typing import Any

from assets.asset_service import get_product_image
from dashboard.snapshot import (
    get_snapshot_alerts,
    get_snapshot_categories,
    get_snapshot_daily_sales,
    get_snapshot_matrix,
    get_snapshot_region_top,
    get_snapshot_regions,
    get_snapshot_sales_rows,
    get_snapshot_stores,
    get_snapshot_summary,
    get_snapshot_top_products,
)
from queries.filters import normalize_filter_values
from queries.products import get_product_explorer_options
from queries.regions import get_region_options


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
        query_filters["region_name"] = normalized.get("region", [])
    if normalized.get("category"):
        query_filters["category_name"] = normalized.get("category", [])
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
        row["image_url"] = image.get("image_url", row.get("image_url", ""))
    return rows


def get_home_sales_rows(filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    normalized = normalize_filter_values(filters)
    snapshot_date = normalized.get("end_date", [""])[0] if normalized.get("end_date") else ""
    rows = get_snapshot_sales_rows({"snapshot_date": [snapshot_date]} if snapshot_date else None)
    for index, row in enumerate(rows, start=1):
        row["排名"] = index
        row["商品代码"] = row.get("product_code", "")
        row["颜色代码"] = row.get("color_code", "")
        row["商品名称"] = row.get("product_name", "")
        row["颜色名称"] = row.get("color_name", "")
        row["品类"] = row.get("category_name", "")
        row["大类"] = row.get("big_category_name", "")
        row["年份"] = row.get("year", "")
        row["季节"] = row.get("season_name", "")
        row["波段"] = row.get("wave", "")
        row["设计师"] = row.get("designer_name", "")
        row["选定价"] = round(float(row.get("standard_price", 0) or 0), 2)
        row["销量"] = int(row.get("sales_qty", 0) or 0)
        row["销售额"] = round(float(row.get("sales_amount", 0) or 0), 2)
    return _attach_image_urls(rows)


def get_home_dashboard(filters: dict[str, Any] | None = None, top_n: int = 20) -> dict[str, Any]:
    normalized = normalize_filter_values(filters)
    snapshot_date = normalized.get("end_date", [""])[0] if normalized.get("end_date") else ""
    snapshot_filter = {"snapshot_date": [snapshot_date]} if snapshot_date else None
    summary = get_snapshot_summary(snapshot_filter)
    region_rows = get_snapshot_regions(snapshot_filter)
    top_products_rows = get_snapshot_top_products(snapshot_filter)
    daily_sales_rows = get_snapshot_daily_sales(snapshot_date)
    category_rows = get_snapshot_categories(snapshot_date)
    store_rows = get_snapshot_stores(snapshot_date)
    region_top = get_snapshot_region_top(snapshot_date)
    matrix_rows = get_snapshot_matrix(snapshot_date)
    alerts = get_snapshot_alerts()
    sales_rows = get_home_sales_rows(filters)

    for index, row in enumerate(region_rows, start=1):
        row["排名"] = index
        row["区域名称"] = row.get("region_name", "")
        row["销量"] = int(row.get("total_qty", 0) or 0)
        row["销售额"] = round(float(row.get("total_amount", 0) or 0), 2)

    by_category = [
        {
            "品类": row.get("category_name", ""),
            "销量": int(row.get("total_qty", 0) or 0),
            "销售额": round(float(row.get("total_amount", 0) or 0), 2),
        }
        for row in category_rows
    ]

    by_store = [
        {
            "商店名称": row.get("store_name", ""),
            "销量": int(row.get("total_qty", 0) or 0),
            "销售额": round(float(row.get("total_amount", 0) or 0), 2),
        }
        for row in store_rows
    ]

    global_top = [dict(row) for row in top_products_rows]
    color_top = _attach_image_urls([dict(row) for row in top_products_rows])
    matrix = _attach_image_urls([dict(row) for row in matrix_rows])

    filters_echo = {
        "date_preset": normalized.get("date_preset", ["week"])[0] if normalized.get("date_preset") else "week",
        "start_date": normalized.get("start_date", [""])[0] if normalized.get("start_date") else "",
        "end_date": normalized.get("end_date", [""])[0] if normalized.get("end_date") else snapshot_date,
        "region": normalized.get("region", ["全国"]) or ["全国"],
        "category": normalized.get("category", []),
        "year_prefix": normalized.get("year_prefix", ["KU"]) or ["KU"],
        "season_code": normalized.get("season_code", ["1"]) or ["1"],
        "wave": normalized.get("wave", []),
        "store": normalized.get("store", []),
        "top_n": [str(top_n)],
    }

    meta = {
        "date_min": snapshot_date,
        "date_max": snapshot_date,
        "default_year_prefix": "KU",
        "default_season_code": "1",
        "year_options": get_home_options().get("year_options", []),
        "season_options": get_home_options().get("season_options", []),
        "wave_options": get_home_options().get("wave_options", []),
        "region_options": get_home_options().get("region_options", []),
        "snapshot_date": snapshot_date,
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
            {"日期": row.get("sale_date", ""), "销量": int(row.get("total_qty", 0) or 0), "销售额": round(float(row.get("total_amount", 0) or 0), 2)}
            for row in daily_sales_rows
        ],
        "matrix": matrix,
        "sales_rows": sales_rows,
        "filters": filters_echo,
        "meta": meta,
        "alerts": alerts,
    }
