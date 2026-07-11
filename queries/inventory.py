from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from assets.asset_service import get_product_image
from queries.retail_queries import _query_all, _query_one
from semantic.inventory import (
    InventoryAnalysisContext,
    InventoryCategorySummary,
    InventoryKPI,
    InventoryPeriod,
    InventoryRegionSummary,
    InventoryStoreSummary,
    InventoryTopProduct,
    InventoryWarehouseSummary,
    InventoryWaveSummary,
)


INVENTORY_BASE_CTE = """
WITH inventory_base AS (
    SELECT
        i.inventory_date,
        i.product_code,
        i.warehouse_code,
        COALESCE(NULLIF(TRIM(i.color_name), ''), '未命名') AS color_name,
        COALESCE(NULLIF(TRIM(i.size_name), ''), '未命名') AS size_name,
        COALESCE(i.raw_inventory_qty, 0) AS raw_inventory_qty,
        COALESCE(i.available_inventory_qty, 0) AS available_inventory_qty,
        i.source_file,
        i.imported_at,
        p.product_name,
        p.category_name,
        p.year_code AS year,
        p.season_name,
        p.major_category_name AS big_category_name,
        p.launch_wave_name AS wave,
        p.standard_retail_price,
        COALESCE(NULLIF(p.cost_price, 0), NULLIF(p.standard_purchase_price, 0), 0) AS unit_cost,
        p.cost_price,
        p.standard_purchase_price,
        w.warehouse_name,
        w.original_code,
        w.warehouse_nature,
        w.warehouse_category_code,
        w.warehouse_category_name,
        w.region_code,
        w.region_name,
        w.channel_code,
        w.channel_name,
        w.warehouse_function,
        w.warehouse_attribute_code,
        w.warehouse_attribute_name,
        COALESCE(w.is_disabled, 0) AS is_disabled,
        w.mapped_store_code,
        w.mapped_store_name,
        COALESCE(w.is_store_warehouse, 0) AS is_store_warehouse
    FROM fact_inventory_snapshot i
    LEFT JOIN dim_product p ON p.product_code = i.product_code
    LEFT JOIN dim_warehouse w ON w.warehouse_code = i.warehouse_code
)
"""


def _scope_clause(scope: str | None) -> tuple[str, list[Any]]:
    selected_scope = (scope or "women").strip().lower() or "women"
    if selected_scope == "women":
        return "AND COALESCE(NULLIF(TRIM(category_name), ''), '') = ?", ["女装"]
    return "", []


def _inventory_where_clause(scope: str | None) -> tuple[str, list[Any]]:
    scope_sql, params = _scope_clause(scope)
    return (f"WHERE inventory_date = ? {scope_sql}" if scope_sql else "WHERE inventory_date = ?"), params


def _latest_inventory_date() -> str:
    row = _query_one(
        "SELECT COALESCE(MAX(inventory_date), '') AS latest_inventory_date FROM fact_inventory_snapshot"
    )
    return str(row.get("latest_inventory_date", "") or "")


def _inventory_period() -> InventoryPeriod:
    inventory_date = _latest_inventory_date()
    if not inventory_date:
        raise LookupError("库存快照为空")
    return InventoryPeriod(inventory_date=inventory_date, label=f"当前库存快照：{inventory_date}")


def get_inventory_kpis(inventory_date: str, scope: str | None = None) -> InventoryKPI:
    where_fragment, params = _inventory_where_clause(scope)
    row = _query_one(
        f"""
        {INVENTORY_BASE_CTE}
        SELECT
            COALESCE(SUM(available_inventory_qty * unit_cost), 0) AS current_inventory_amount,
            COALESCE(SUM(available_inventory_qty), 0) AS current_inventory_qty,
            COUNT(DISTINCT CASE WHEN available_inventory_qty > 0 THEN product_code END) AS inventory_sku_count,
            COUNT(DISTINCT warehouse_code) AS warehouse_count,
            COUNT(DISTINCT CASE WHEN is_store_warehouse = 1 THEN warehouse_code END) AS store_warehouse_count
        FROM inventory_base
        {where_fragment}
        """,
        [inventory_date] + params,
    )
    return InventoryKPI.from_query_row(row)


def get_inventory_top_products(inventory_date: str, scope: str | None = None, limit: int = 20) -> list[InventoryTopProduct]:
    where_fragment, params = _inventory_where_clause(scope)
    rows = _query_all(
        f"""
        {INVENTORY_BASE_CTE}
        SELECT
            product_code,
            MAX(product_name) AS product_name,
            COALESCE(SUM(available_inventory_qty), 0) AS inventory_qty,
            COALESCE(SUM(available_inventory_qty * unit_cost), 0) AS inventory_amount,
            COUNT(DISTINCT CASE WHEN available_inventory_qty > 0 THEN warehouse_code END) AS warehouse_coverage,
            CASE
                WHEN COALESCE(SUM(available_inventory_qty), 0) > 0 THEN SUM(available_inventory_qty * unit_cost) * 1.0 / SUM(available_inventory_qty)
                ELSE NULL
            END AS average_cost
        FROM inventory_base
        {where_fragment}
        GROUP BY product_code
        ORDER BY inventory_amount DESC, inventory_qty DESC, product_code ASC
        LIMIT ?
        """,
        [inventory_date] + params + [int(limit)],
    )
    products: list[InventoryTopProduct] = []
    for index, row in enumerate(rows, start=1):
        image = get_product_image(str(row.get("product_code", "") or ""))
        payload = dict(row)
        payload.update(image)
        payload["rank"] = index
        products.append(InventoryTopProduct.from_query_row(payload))
    return products


def get_inventory_warehouse_ranking(inventory_date: str, scope: str | None = None, limit: int = 20) -> list[InventoryWarehouseSummary]:
    where_fragment, params = _inventory_where_clause(scope)
    rows = _query_all(
        f"""
        {INVENTORY_BASE_CTE}
        SELECT
            warehouse_code,
            COALESCE(NULLIF(TRIM(warehouse_name), ''), warehouse_code) AS warehouse_name,
            COALESCE(
                NULLIF(TRIM(warehouse_function), ''),
                NULLIF(TRIM(warehouse_nature), ''),
                NULLIF(TRIM(warehouse_attribute_name), ''),
                NULLIF(TRIM(warehouse_category_name), ''),
                '未分类'
            ) AS warehouse_type,
            COALESCE(SUM(available_inventory_qty * unit_cost), 0) AS inventory_amount,
            COALESCE(SUM(available_inventory_qty), 0) AS inventory_qty,
            COUNT(DISTINCT CASE WHEN available_inventory_qty > 0 THEN product_code END) AS sku_count,
            COALESCE(is_store_warehouse, 0) AS is_store_warehouse,
            COALESCE(NULLIF(TRIM(mapped_store_name), ''), '') AS mapped_store_name
        FROM inventory_base
        {where_fragment}
        GROUP BY warehouse_code, warehouse_name, warehouse_type, is_store_warehouse, mapped_store_name
        ORDER BY inventory_amount DESC, inventory_qty DESC, warehouse_name ASC
        LIMIT ?
        """,
        [inventory_date] + params + [int(limit)],
    )
    summaries: list[InventoryWarehouseSummary] = []
    for index, row in enumerate(rows, start=1):
        payload = dict(row)
        payload["rank"] = index
        summaries.append(InventoryWarehouseSummary.from_query_row(payload))
    return summaries


def get_inventory_store_ranking(inventory_date: str, scope: str | None = None, limit: int = 20) -> list[InventoryStoreSummary]:
    where_fragment, params = _inventory_where_clause(scope)
    rows = _query_all(
        f"""
        {INVENTORY_BASE_CTE}
        SELECT
            COALESCE(NULLIF(TRIM(mapped_store_code), ''), '') AS store_code,
            COALESCE(NULLIF(TRIM(mapped_store_name), ''), '未绑定门店') AS store_name,
            COALESCE(SUM(available_inventory_qty * unit_cost), 0) AS inventory_amount,
            COALESCE(SUM(available_inventory_qty), 0) AS inventory_qty,
            COUNT(DISTINCT CASE WHEN available_inventory_qty > 0 THEN product_code END) AS sku_count
        FROM inventory_base
        {where_fragment}
          AND COALESCE(NULLIF(TRIM(mapped_store_code), ''), '') <> ''
        GROUP BY store_code, store_name
        ORDER BY inventory_amount DESC, inventory_qty DESC, store_name ASC
        LIMIT ?
        """,
        [inventory_date] + params + [int(limit)],
    )
    summaries: list[InventoryStoreSummary] = []
    for index, row in enumerate(rows, start=1):
        payload = dict(row)
        payload["rank"] = index
        summaries.append(InventoryStoreSummary.from_query_row(payload))
    return summaries


def get_inventory_region_summary(inventory_date: str, scope: str | None = None) -> list[InventoryRegionSummary]:
    where_fragment, params = _inventory_where_clause(scope)
    total_row = _query_one(
        f"""
        {INVENTORY_BASE_CTE}
        SELECT COALESCE(SUM(available_inventory_qty * unit_cost), 0) AS inventory_amount
        FROM inventory_base
        {where_fragment}
        """,
        [inventory_date] + params,
    )
    total_amount = float(total_row.get("inventory_amount", 0) or 0)
    rows = _query_all(
        f"""
        {INVENTORY_BASE_CTE}
        SELECT
            COALESCE(NULLIF(TRIM(region_name), ''), '未分区') AS region_name,
            COALESCE(SUM(available_inventory_qty * unit_cost), 0) AS inventory_amount,
            COALESCE(SUM(available_inventory_qty), 0) AS inventory_qty
        FROM inventory_base
        {where_fragment}
        GROUP BY COALESCE(NULLIF(TRIM(region_name), ''), '未分区')
        ORDER BY inventory_amount DESC, inventory_qty DESC, region_name ASC
        """,
        [inventory_date] + params,
    )
    return [
        InventoryRegionSummary(
            region_name=str(row.get("region_name", "") or "未分区"),
            inventory_amount=float(row.get("inventory_amount", 0) or 0),
            inventory_qty=float(row.get("inventory_qty", 0) or 0),
            contribution_rate=(float(row.get("inventory_amount", 0) or 0) / total_amount) if total_amount else 0.0,
        )
        for row in rows
    ]


def get_inventory_category_summary(inventory_date: str, scope: str | None = None) -> list[InventoryCategorySummary]:
    where_fragment, params = _inventory_where_clause(scope)
    category_column = "big_category_name" if (scope or "women").strip().lower() == "women" else "category_name"
    total_row = _query_one(
        f"""
        {INVENTORY_BASE_CTE}
        SELECT COALESCE(SUM(available_inventory_qty * unit_cost), 0) AS inventory_amount
        FROM inventory_base
        {where_fragment}
        """,
        [inventory_date] + params,
    )
    total_amount = float(total_row.get("inventory_amount", 0) or 0)
    rows = _query_all(
        f"""
        {INVENTORY_BASE_CTE}
        SELECT
            COALESCE(NULLIF(TRIM({category_column}), ''), '未分类') AS category_name,
            COALESCE(SUM(available_inventory_qty * unit_cost), 0) AS inventory_amount,
            COALESCE(SUM(available_inventory_qty), 0) AS inventory_qty
        FROM inventory_base
        {where_fragment}
        GROUP BY COALESCE(NULLIF(TRIM({category_column}), ''), '未分类')
        ORDER BY inventory_amount DESC, inventory_qty DESC, category_name ASC
        """,
        [inventory_date] + params,
    )
    return [
        InventoryCategorySummary(
            category_name=str(row.get("category_name", "") or "未分类"),
            inventory_amount=float(row.get("inventory_amount", 0) or 0),
            inventory_qty=float(row.get("inventory_qty", 0) or 0),
            contribution_rate=(float(row.get("inventory_amount", 0) or 0) / total_amount) if total_amount else 0.0,
        )
        for row in rows
    ]


def get_inventory_wave_summary(inventory_date: str, scope: str | None = None) -> list[InventoryWaveSummary]:
    where_fragment, params = _inventory_where_clause(scope)
    total_row = _query_one(
        f"""
        {INVENTORY_BASE_CTE}
        SELECT COALESCE(SUM(available_inventory_qty * unit_cost), 0) AS inventory_amount
        FROM inventory_base
        {where_fragment}
        """,
        [inventory_date] + params,
    )
    total_amount = float(total_row.get("inventory_amount", 0) or 0)
    rows = _query_all(
        f"""
        {INVENTORY_BASE_CTE}
        SELECT
            COALESCE(NULLIF(TRIM(wave), ''), '未识别') AS wave_name,
            COALESCE(SUM(available_inventory_qty * unit_cost), 0) AS inventory_amount,
            COALESCE(SUM(available_inventory_qty), 0) AS inventory_qty
        FROM inventory_base
        {where_fragment}
        GROUP BY COALESCE(NULLIF(TRIM(wave), ''), '未识别')
        ORDER BY inventory_amount DESC, inventory_qty DESC, wave_name ASC
        """,
        [inventory_date] + params,
    )
    return [
        InventoryWaveSummary(
            wave_name=str(row.get("wave_name", "") or "未识别"),
            inventory_amount=float(row.get("inventory_amount", 0) or 0),
            inventory_qty=float(row.get("inventory_qty", 0) or 0),
            contribution_rate=(float(row.get("inventory_amount", 0) or 0) / total_amount) if total_amount else 0.0,
        )
        for row in rows
    ]


def get_inventory_analysis_context(scope: str | None = None) -> InventoryAnalysisContext:
    selected_scope = (scope or "women").strip().lower() or "women"
    if selected_scope not in {"women", "all"}:
        selected_scope = "women"
    period = _inventory_period()
    kpis = get_inventory_kpis(period.inventory_date, scope=selected_scope)
    top_products = get_inventory_top_products(period.inventory_date, scope=selected_scope, limit=20)
    warehouse_ranking = get_inventory_warehouse_ranking(period.inventory_date, scope=selected_scope, limit=20)
    store_ranking = get_inventory_store_ranking(period.inventory_date, scope=selected_scope, limit=20)
    region_summary = get_inventory_region_summary(period.inventory_date, scope=selected_scope)
    category_summary = get_inventory_category_summary(period.inventory_date, scope=selected_scope)
    wave_summary = get_inventory_wave_summary(period.inventory_date, scope=selected_scope)
    return InventoryAnalysisContext(
        period=period,
        kpis=kpis,
        top_products=top_products,
        warehouse_ranking=warehouse_ranking,
        store_ranking=store_ranking,
        region_summary=region_summary,
        category_summary=category_summary,
        wave_summary=wave_summary,
        selected_scope=selected_scope,
    )