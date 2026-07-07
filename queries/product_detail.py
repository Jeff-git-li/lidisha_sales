from __future__ import annotations

from typing import Any

from assets.asset_service import get_product_image
from queries.filters import build_where_clause
from queries.retail_queries import _query_all, _query_one
from semantic.product_detail import (
    ProductAIContext,
    ProductColorSummary,
    ProductDetail,
    ProductDetailProfile,
    ProductRegionSummary,
    ProductSalesSummary,
    ProductSizeSummary,
    ProductStoreSummary,
    ProductTrend,
)


def _base_filters(product_code: str, filters: dict[str, Any] | None = None) -> dict[str, Any]:
    query_filters = dict(filters or {})
    query_filters["product_code"] = [product_code]
    return query_filters


def get_product_detail(product_code: str, filters: dict[str, Any] | None = None) -> ProductDetail:
    base_filters = _base_filters(product_code, filters)
    where_sql, params = build_where_clause(base_filters, core_only=False)
    sql = f"""
    WITH joined AS (
        SELECT
            f.product_code AS product_code,
            f.sale_date,
            f.date_key,
            f.color_code,
            f.color_name,
            f.size_code,
            f.size_name,
            f.store_code,
            f.document_no,
            f.document_type,
            f.qty,
            f.standard_amount,
            f.amount,
            f.standard_price,
            f.unit_price,
            p.product_name,
            p.image_path,
            p.year_code AS year,
            p.season_name,
            p.launch_wave_name AS wave,
            p.designer_name,
            p.category_name,
            p.major_category_name AS big_category_name,
            p.brand_name,
            p.series_name,
            p.standard_retail_price AS dim_standard_price,
            s.store_name,
            s.region_name,
            s.channel_code,
            s.store_type_name
        FROM fact_retail_sales f
        LEFT JOIN dim_product p ON p.product_code = f.product_code
        LEFT JOIN dim_store s ON s.store_code = f.store_code
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
        MAX(brand_name) AS brand_name,
        MAX(series_name) AS series_name,
        MAX(dim_standard_price) AS standard_price,
        COALESCE(SUM(qty), 0) AS sales_qty,
        COALESCE(SUM(amount), 0) AS sales_amount,
        COALESCE(SUM(standard_amount), 0) AS standard_amount,
        CASE WHEN COALESCE(SUM(qty), 0) = 0 THEN 0 ELSE COALESCE(SUM(amount), 0) / COALESCE(SUM(qty), 1) END AS average_unit_price,
        CASE WHEN COALESCE(SUM(qty), 0) = 0 THEN 0 ELSE COALESCE(SUM(standard_amount), 0) / COALESCE(SUM(qty), 1) END AS average_standard_price,
        CASE WHEN COALESCE(SUM(standard_amount), 0) = 0 THEN 0 ELSE COALESCE(SUM(amount), 0) * 1.0 / COALESCE(SUM(standard_amount), 1) END AS average_discount_rate,
        COUNT(*) AS transaction_count,
        COUNT(DISTINCT store_code) AS store_count,
        COUNT(DISTINCT color_code) AS color_count,
        COUNT(DISTINCT size_code) AS size_count
    FROM joined
    {where_sql}
    GROUP BY product_code
    LIMIT 1
    """
    row = _query_one(sql, params)
    if not row:
        raise LookupError(f"Product not found: {product_code}")

    image = get_product_image(product_code)
    profile_row = dict(row)
    profile_row.update(image)
    profile = ProductDetailProfile.from_query_row(profile_row)
    sales_summary = ProductSalesSummary.from_query_row(row)
    trend = ProductTrend.from_query_rows(get_product_sales_trend(product_code, filters))
    region_summary = ProductRegionSummary.from_query_rows(get_product_region_distribution(product_code, filters))
    store_summary = ProductStoreSummary.from_query_rows(get_product_store_distribution(product_code, filters))
    color_summary = ProductColorSummary.from_query_rows(get_product_color_distribution(product_code, filters))
    size_summary = ProductSizeSummary.from_query_rows(get_product_size_distribution(product_code, filters))
    ai_context = ProductAIContext(
        profile=profile,
        sales_summary=sales_summary,
        trend_summary=trend,
        region_summary=region_summary,
        store_summary=store_summary,
        color_summary=color_summary,
        size_summary=size_summary,
        latest_activity=get_product_latest_activity(product_code, filters),
    )
    return ProductDetail(
        profile=profile,
        sales_summary=sales_summary,
        trend=trend,
        region_summary=region_summary,
        store_summary=store_summary,
        color_summary=color_summary,
        size_summary=size_summary,
        ai_context=ai_context,
    )


def get_product_sales_summary(product_code: str, filters: dict[str, Any] | None = None) -> ProductSalesSummary:
    detail = get_product_detail(product_code, filters)
    return detail.sales_summary


def get_product_sales_trend(product_code: str, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    where_sql, params = build_where_clause(_base_filters(product_code, filters), core_only=False)
    sql = f"""
    SELECT
        f.sale_date,
        COALESCE(SUM(f.qty), 0) AS sales_qty,
        COALESCE(SUM(f.amount), 0) AS sales_amount,
        COALESCE(SUM(f.standard_amount), 0) AS standard_amount,
        COUNT(*) AS transaction_count
    FROM fact_retail_sales f
    {where_sql}
    GROUP BY f.sale_date
    ORDER BY f.sale_date
    """
    return _query_all(sql, params)


def get_product_color_distribution(product_code: str, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    where_sql, params = build_where_clause(_base_filters(product_code, filters), core_only=False)
    sql = f"""
    SELECT
        f.color_code,
        COALESCE(NULLIF(f.color_name, ''), '未命名') AS color_name,
        COALESCE(SUM(f.qty), 0) AS sales_qty,
        COALESCE(SUM(f.amount), 0) AS sales_amount,
        COUNT(*) AS transaction_count
    FROM fact_retail_sales f
    {where_sql}
    GROUP BY f.color_code, COALESCE(NULLIF(f.color_name, ''), '未命名')
    ORDER BY sales_amount DESC, sales_qty DESC, color_name
    """
    return _query_all(sql, params)


def get_product_size_distribution(product_code: str, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    where_sql, params = build_where_clause(_base_filters(product_code, filters), core_only=False)
    sql = f"""
    SELECT
        f.size_code,
        COALESCE(NULLIF(f.size_name, ''), '未命名') AS size_name,
        COALESCE(SUM(f.qty), 0) AS sales_qty,
        COALESCE(SUM(f.amount), 0) AS sales_amount,
        COUNT(*) AS transaction_count
    FROM fact_retail_sales f
    {where_sql}
    GROUP BY f.size_code, COALESCE(NULLIF(f.size_name, ''), '未命名')
    ORDER BY sales_amount DESC, sales_qty DESC, size_name
    """
    return _query_all(sql, params)


def get_product_region_distribution(product_code: str, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    where_sql, params = build_where_clause(_base_filters(product_code, filters), core_only=False)
    sql = f"""
    SELECT
        COALESCE(s.region_name, '未分区') AS region_name,
        COALESCE(SUM(f.qty), 0) AS sales_qty,
        COALESCE(SUM(f.amount), 0) AS sales_amount,
        COUNT(DISTINCT f.store_code) AS store_count
    FROM fact_retail_sales f
    LEFT JOIN dim_store s ON s.store_code = f.store_code
    {where_sql}
    GROUP BY COALESCE(s.region_name, '未分区')
    ORDER BY sales_amount DESC, sales_qty DESC, region_name
    """
    return _query_all(sql, params)


def get_product_store_distribution(product_code: str, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    where_sql, params = build_where_clause(_base_filters(product_code, filters), core_only=False)
    sql = f"""
    SELECT
        f.store_code,
        COALESCE(s.store_name, f.store_code) AS store_name,
        COALESCE(s.region_name, '未分区') AS region_name,
        COALESCE(SUM(f.qty), 0) AS sales_qty,
        COALESCE(SUM(f.amount), 0) AS sales_amount,
        COUNT(*) AS transaction_count
    FROM fact_retail_sales f
    LEFT JOIN dim_store s ON s.store_code = f.store_code
    {where_sql}
    GROUP BY f.store_code, COALESCE(s.store_name, f.store_code), COALESCE(s.region_name, '未分区')
    ORDER BY sales_amount DESC, sales_qty DESC, store_name
    """
    return _query_all(sql, params)


def get_product_latest_activity(product_code: str, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    where_sql, params = build_where_clause(_base_filters(product_code, filters), core_only=False)
    sql = f"""
    SELECT
        f.sale_date,
        f.document_no,
        f.document_type,
        f.store_code,
        f.color_code,
        f.color_name,
        f.size_code,
        f.size_name,
        f.qty,
        f.standard_amount,
        f.amount,
        f.standard_price,
        f.unit_price
    FROM fact_retail_sales f
    {where_sql}
    ORDER BY f.sale_date DESC, f.document_no DESC
    LIMIT 20
    """
    return _query_all(sql, params)