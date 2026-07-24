from __future__ import annotations

from datetime import date, timedelta
from dataclasses import dataclass
from typing import Any

from assets.asset_service import get_product_image
from queries.filters import build_where_clause
from queries.retail_queries import JOINED_CTE, _query_all, _query_one
from semantic.inventory import (
    InventoryAnalysisContext,
    InventoryChannelOption,
    InventoryCategorySummary,
    InventoryHealthSummary,
    InventoryKPI,
    InventoryPeriod,
    InventoryRegionSummary,
    InventorySellThroughProduct,
    InventoryStoreSummary,
    InventoryStoreOption,
    InventoryTopProduct,
    InventoryWarehouseSummary,
)


VALID_INVENTORY_BASES = {"terminal", "all"}
VALID_PRODUCT_SORTS = {"quarter_sales_qty", "quarter_sell_through_rate", "current_inventory_qty", "cumulative_sell_through_rate"}


@dataclass(slots=True)
class InventoryDateWindow:
    inventory_snapshot_date: str
    latest_sales_date: str
    effective_sales_date: str
    quarter_start_date: str


CHANNEL_JOIN_CTE = """
LEFT JOIN dim_store s ON s.store_code = w.mapped_store_code
LEFT JOIN dim_channel c ON c.channel_code = s.channel_code
"""


INVENTORY_BASE_DEFINITION = """
inventory_base AS (
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
        COALESCE(NULLIF(TRIM(s.store_code), ''), '') AS store_code,
        COALESCE(NULLIF(TRIM(s.store_name), ''), '') AS store_name,
        COALESCE(NULLIF(TRIM(s.channel_code), ''), '') AS store_channel_code,
        COALESCE(NULLIF(TRIM(c.channel_name), ''), '') AS store_channel_name,
        COALESCE(NULLIF(TRIM(s.region_name), ''), '') AS store_region_name,
        COALESCE(w.is_store_warehouse, 0) AS is_store_warehouse
    FROM fact_inventory_snapshot i
    LEFT JOIN dim_product p ON p.product_code = i.product_code
    LEFT JOIN dim_warehouse w ON w.warehouse_code = i.warehouse_code
    LEFT JOIN dim_store s ON s.store_code = w.mapped_store_code
    LEFT JOIN dim_channel c ON c.channel_code = s.channel_code
)
"""


def _compose_cte(*definitions: str) -> str:
    cleaned: list[str] = []
    for definition in definitions:
        text = definition.strip()
        if text.upper().startswith("WITH "):
            text = text[5:].strip()
        cleaned.append(text)
    return "WITH " + ",\n".join(cleaned)


def _inventory_base_cte(include_joined: bool = False) -> str:
    if include_joined:
        return _compose_cte(INVENTORY_BASE_DEFINITION, JOINED_CTE)
    return _compose_cte(INVENTORY_BASE_DEFINITION)


def _scope_clause(scope: str | None) -> tuple[str, list[Any]]:
    selected_scope = (scope or "women").strip().lower() or "women"
    if selected_scope == "women":
        return "AND COALESCE(NULLIF(TRIM(category_name), ''), '') = ?", ["女装"]
    return "", []


def _normalize_inventory_basis(inventory_basis: str | None) -> str:
    selected_basis = (inventory_basis or "terminal").strip().lower() or "terminal"
    if selected_basis not in VALID_INVENTORY_BASES:
        return "terminal"
    return selected_basis


def _inventory_basis_label(inventory_basis: str | None) -> str:
    return "终端库存" if _normalize_inventory_basis(inventory_basis) == "terminal" else "全渠道库存"


def _normalize_product_sort(product_sort: str | None) -> str:
    selected_sort = (product_sort or "quarter_sales_qty").strip().lower() or "quarter_sales_qty"
    if selected_sort not in VALID_PRODUCT_SORTS:
        return "quarter_sales_qty"
    return selected_sort


def _quarter_start(date_value: str) -> str:
    current = date.fromisoformat(date_value)
    month = ((current.month - 1) // 3) * 3 + 1
    return date(current.year, month, 1).isoformat()


def _inventory_where_clause(scope: str | None) -> tuple[str, list[Any]]:
    scope_sql, params = _scope_clause(scope)
    return (f"WHERE inventory_date = ? {scope_sql}" if scope_sql else "WHERE inventory_date = ?"), params


def _inventory_channel_store_clause(scope: str | None, channel_code: str | None = None, store_code: str | None = None) -> tuple[str, list[Any]]:
    where_parts = ["inventory_date = ?"]
    params: list[Any] = []
    scope_sql, scope_params = _scope_clause(scope)
    if scope_sql:
        where_parts.append(scope_sql.replace("AND ", "", 1))
        params.extend(scope_params)
    channel_code = (channel_code or "").strip()
    store_code = (store_code or "").strip()
    if channel_code:
        where_parts.append("channel_code = ?")
        params.append(channel_code)
    if store_code:
        where_parts.append("mapped_store_code = ?")
        params.append(store_code)
    return "WHERE " + " AND ".join(where_parts), params


def _channel_store_inventory_clause(scope: str | None, channel_code: str | None = None, store_code: str | None = None, inventory_basis: str | None = None) -> tuple[str, list[Any]]:
    selected_scope = (scope or "women").strip().lower() or "women"
    clauses: list[str] = ["inventory_date = ?"]
    params: list[Any] = []
    if selected_scope == "women":
        clauses.append("COALESCE(NULLIF(TRIM(category_name), ''), '') = ?")
        params.append("女装")
    if _normalize_inventory_basis(inventory_basis) == "terminal":
        clauses.append("COALESCE(is_store_warehouse, 0) = 1")
    channel_code = (channel_code or "").strip()
    store_code = (store_code or "").strip()
    if channel_code:
        clauses.append("COALESCE(NULLIF(TRIM(store_channel_code), ''), '') = ?")
        params.append(channel_code)
    if store_code:
        clauses.append("COALESCE(NULLIF(TRIM(store_code), ''), '') = ?")
        params.append(store_code)
    return "WHERE " + " AND ".join(clauses), params


def _latest_inventory_date() -> str:
    row = _query_one(
        "SELECT COALESCE(MAX(inventory_date), '') AS latest_inventory_date FROM fact_inventory_snapshot"
    )
    return str(row.get("latest_inventory_date", "") or "")


def _inventory_period() -> InventoryPeriod:
    inventory_date = _latest_inventory_date()
    if not inventory_date:
        raise LookupError("库存快照为空")
    return InventoryPeriod(
        inventory_date=inventory_date,
        label=f"当前库存快照：{inventory_date}",
        inventory_snapshot_date=inventory_date,
    )


def _sales_filter_args(scope: str | None, channel_code: str | None = None, store_code: str | None = None, start_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
    filters: dict[str, Any] = {"scope": [scope or "women"]}
    if start_date:
        filters["start_date"] = [start_date]
    if end_date:
        filters["end_date"] = [end_date]
    if channel_code:
        filters["channel_code"] = [channel_code]
    if store_code:
        filters["store_code"] = [store_code]
    return filters


def _latest_sales_date(scope: str | None = None, channel_code: str | None = None, store_code: str | None = None) -> str:
    where_sql, params = build_where_clause(
        _sales_filter_args(scope, channel_code=channel_code, store_code=store_code),
        core_only=False,
    )
    row = _query_one(
        f"""
        {_inventory_base_cte(include_joined=True)}
        SELECT COALESCE(MAX(sale_date), '') AS latest_sales_date
        FROM joined
        {where_sql}
        """,
        params,
    )
    return str(row.get("latest_sales_date", "") or "")


def _inventory_date_window(scope: str | None = None, channel_code: str | None = None, store_code: str | None = None) -> InventoryDateWindow:
    inventory_snapshot_date = _latest_inventory_date()
    if not inventory_snapshot_date:
        raise LookupError("库存快照为空")
    latest_sales_date = _latest_sales_date(scope=scope, channel_code=channel_code, store_code=store_code)
    if latest_sales_date:
        effective_sales_date = min(inventory_snapshot_date, latest_sales_date)
    else:
        effective_sales_date = inventory_snapshot_date
    quarter_start_date = _quarter_start(effective_sales_date)
    return InventoryDateWindow(
        inventory_snapshot_date=inventory_snapshot_date,
        latest_sales_date=latest_sales_date,
        effective_sales_date=effective_sales_date,
        quarter_start_date=quarter_start_date,
    )


def _sales_window(inventory_date: str) -> tuple[str, str]:
    end_date = date.fromisoformat(inventory_date)
    start_date = end_date - timedelta(days=29)
    return start_date.isoformat(), end_date.isoformat()


def _sales_filters(scope: str | None, channel_code: str | None = None, store_code: str | None = None, inventory_date: str | None = None) -> dict[str, Any]:
    start_date, end_date = _sales_window(inventory_date or _latest_inventory_date())
    filters: dict[str, Any] = {
        "scope": [scope or "women"],
        "start_date": [start_date],
        "end_date": [end_date],
    }
    if channel_code:
        filters["channel_code"] = [channel_code]
    if store_code:
        filters["store_code"] = [store_code]
    return filters


def _sales_summary(inventory_date: str, scope: str | None = None, channel_code: str | None = None, store_code: str | None = None) -> dict[str, Any]:
    where_sql, params = build_where_clause(_sales_filters(scope, channel_code=channel_code, store_code=store_code, inventory_date=inventory_date), core_only=False)
    row = _query_one(
        f"""
        {_inventory_base_cte(include_joined=True)}
        SELECT
            COALESCE(SUM(qty), 0) AS last_30_days_sales,
            COUNT(*) AS sales_rows
        FROM joined
        {where_sql}
        """,
        params,
    )
    return row


def _sales_metrics(inventory_date: str, scope: str | None = None, channel_code: str | None = None, store_code: str | None = None, inventory_qty: float = 0.0) -> tuple[float | None, float | None, float | None, bool]:
    row = _sales_summary(inventory_date, scope=scope, channel_code=channel_code, store_code=store_code)
    sales_rows = int(row.get("sales_rows", 0) or 0)
    if sales_rows <= 0:
        return None, None, None, False
    last_30_days_sales = float(row.get("last_30_days_sales", 0) or 0)
    sell_through_rate = None
    if last_30_days_sales + inventory_qty > 0:
        sell_through_rate = last_30_days_sales / (last_30_days_sales + inventory_qty)
    inventory_days = None
    if last_30_days_sales > 0:
        inventory_days = inventory_qty / (last_30_days_sales / 30.0)
    return last_30_days_sales, sell_through_rate, inventory_days, True


def _sell_through_rate(sales_qty: float, inventory_qty: float) -> float | None:
    denominator = sales_qty + inventory_qty
    if denominator <= 0:
        return None
    return sales_qty / denominator


def _product_sort_key(row: dict[str, Any], product_sort: str) -> tuple[Any, ...]:
    numeric = row.get(product_sort)
    normalized_value = float(numeric) if numeric is not None else -1.0
    return (
        normalized_value,
        float(row.get("quarter_sales_qty", 0) or 0),
        float(row.get("cumulative_sales_qty", 0) or 0),
        float(row.get("current_inventory_qty", 0) or 0),
        str(row.get("product_code", "") or ""),
    )


def _product_sellthrough_rows(date_window: InventoryDateWindow, scope: str | None = None, inventory_basis: str | None = None, channel_code: str | None = None, store_code: str | None = None) -> list[dict[str, Any]]:
    inventory_where_sql, inventory_params = _channel_store_inventory_clause(scope, channel_code=channel_code, store_code=store_code, inventory_basis=inventory_basis)
    quarter_sales_where_sql, quarter_sales_params = build_where_clause(
        _sales_filter_args(scope, channel_code=channel_code, store_code=store_code, end_date=date_window.effective_sales_date),
        core_only=False,
    )
    cumulative_sales_where_sql, cumulative_sales_params = build_where_clause(
        _sales_filter_args(
            scope,
            channel_code=channel_code,
            store_code=store_code,
            end_date=date_window.effective_sales_date,
        ),
        core_only=False,
    )
    sql = f"""
    {_inventory_base_cte(include_joined=True)},
    inventory_by_product AS (
        SELECT
            product_code,
            MAX(product_name) AS product_name,
            MAX(category_name) AS category_name,
            MAX(big_category_name) AS big_category_name,
            COALESCE(SUM(available_inventory_qty), 0) AS current_inventory_qty,
            COALESCE(SUM(available_inventory_qty * unit_cost), 0) AS inventory_amount,
            COUNT(DISTINCT CASE WHEN available_inventory_qty > 0 AND COALESCE(NULLIF(TRIM(store_code), ''), '') <> '' THEN store_code END) AS inventory_store_coverage
        FROM inventory_base
        {inventory_where_sql}
        GROUP BY product_code
    ),
    quarter_sales_by_product AS (
        SELECT
            product_code,
            MAX(product_name) AS product_name,
            MAX(category_name) AS category_name,
            MAX(big_category_name) AS big_category_name,
            COALESCE(SUM(qty), 0) AS quarter_sales_qty,
            COALESCE(SUM(effective_amount), 0) AS quarter_sales_amount,
            COUNT(DISTINCT store_code) AS quarter_store_coverage
        FROM joined
        {quarter_sales_where_sql}
        GROUP BY product_code
    ),
    cumulative_sales_by_product AS (
        SELECT
            product_code,
            MAX(product_name) AS product_name,
            MAX(category_name) AS category_name,
            MAX(big_category_name) AS big_category_name,
            COALESCE(SUM(qty), 0) AS cumulative_sales_qty,
            COALESCE(SUM(effective_amount), 0) AS cumulative_sales_amount,
            COUNT(DISTINCT store_code) AS cumulative_store_coverage
        FROM joined
        {cumulative_sales_where_sql}
        GROUP BY product_code
    ),
    product_keys AS (
        SELECT product_code FROM inventory_by_product
        UNION
        SELECT product_code FROM quarter_sales_by_product
        UNION
        SELECT product_code FROM cumulative_sales_by_product
    )
    SELECT
        keys.product_code,
        COALESCE(inv.product_name, quarter.product_name, cumulative.product_name, keys.product_code) AS product_name,
        COALESCE(NULLIF(TRIM(inv.category_name), ''), NULLIF(TRIM(quarter.category_name), ''), NULLIF(TRIM(cumulative.category_name), ''), '未分类') AS category_name,
        COALESCE(NULLIF(TRIM(inv.big_category_name), ''), NULLIF(TRIM(quarter.big_category_name), ''), NULLIF(TRIM(cumulative.big_category_name), ''), '未分类') AS big_category_name,
        COALESCE(inv.current_inventory_qty, 0) AS current_inventory_qty,
        COALESCE(inv.inventory_amount, 0) AS inventory_amount,
        COALESCE(quarter.quarter_sales_qty, 0) AS quarter_sales_qty,
        COALESCE(quarter.quarter_sales_amount, 0) AS quarter_sales_amount,
        COALESCE(cumulative.cumulative_sales_qty, 0) AS cumulative_sales_qty,
        COALESCE(cumulative.cumulative_sales_amount, 0) AS cumulative_sales_amount,
        CASE
            WHEN COALESCE(quarter.quarter_sales_qty, 0) + COALESCE(inv.current_inventory_qty, 0) > 0 THEN COALESCE(quarter.quarter_sales_qty, 0) * 1.0 / (COALESCE(quarter.quarter_sales_qty, 0) + COALESCE(inv.current_inventory_qty, 0))
            ELSE NULL
        END AS quarter_sell_through_rate,
        CASE
            WHEN COALESCE(cumulative.cumulative_sales_qty, 0) + COALESCE(inv.current_inventory_qty, 0) > 0 THEN COALESCE(cumulative.cumulative_sales_qty, 0) * 1.0 / (COALESCE(cumulative.cumulative_sales_qty, 0) + COALESCE(inv.current_inventory_qty, 0))
            ELSE NULL
        END AS cumulative_sell_through_rate,
        MAX(COALESCE(inv.inventory_store_coverage, 0), COALESCE(quarter.quarter_store_coverage, 0), COALESCE(cumulative.cumulative_store_coverage, 0)) AS store_coverage
    FROM product_keys keys
    LEFT JOIN inventory_by_product inv ON inv.product_code = keys.product_code
    LEFT JOIN quarter_sales_by_product quarter ON quarter.product_code = keys.product_code
    LEFT JOIN cumulative_sales_by_product cumulative ON cumulative.product_code = keys.product_code
    WHERE COALESCE(inv.current_inventory_qty, 0) <> 0
       OR COALESCE(quarter.quarter_sales_qty, 0) <> 0
       OR COALESCE(cumulative.cumulative_sales_qty, 0) <> 0
    """
    params = [date_window.inventory_snapshot_date] + inventory_params + quarter_sales_params + cumulative_sales_params
    return _query_all(sql, params)


def _build_kpis_from_rows(date_window: InventoryDateWindow, rows: list[dict[str, Any]], scope: str | None = None, channel_code: str | None = None, store_code: str | None = None, inventory_basis: str | None = None) -> InventoryKPI:
    base_row = get_inventory_quantity_summary(
        date_window.inventory_snapshot_date,
        scope=scope,
        channel_code=channel_code,
        store_code=store_code,
        inventory_basis=inventory_basis,
    )
    inventory_qty = float(base_row.get("current_inventory_qty", 0) or 0)
    quarter_sales_qty = sum(float(row.get("quarter_sales_qty", 0) or 0) for row in rows)
    cumulative_sales_qty = sum(float(row.get("cumulative_sales_qty", 0) or 0) for row in rows)
    last_30_days_sales, sell_through_rate, inventory_days, sales_available = _sales_metrics(
        date_window.inventory_snapshot_date,
        scope=scope,
        channel_code=channel_code,
        store_code=store_code,
        inventory_qty=inventory_qty,
    )
    return InventoryKPI(
        current_inventory_amount=float(base_row.get("current_inventory_amount", 0) or 0),
        current_inventory_qty=inventory_qty,
        inventory_sku_count=int(base_row.get("inventory_sku_count", 0) or 0),
        warehouse_count=int(base_row.get("store_count", 0) or 0),
        store_warehouse_count=int(base_row.get("store_count", 0) or 0),
        last_30_days_sales=last_30_days_sales,
        sell_through_rate=sell_through_rate,
        inventory_days=inventory_days,
        quarter_sell_through_rate=_sell_through_rate(quarter_sales_qty, inventory_qty),
        cumulative_sell_through_rate=_sell_through_rate(cumulative_sales_qty, inventory_qty),
        sales_available=sales_available,
    )


def _build_kpis_from_rows(date_window: InventoryDateWindow, rows: list[dict[str, Any]], scope: str | None = None, channel_code: str | None = None, store_code: str | None = None, inventory_basis: str | None = None) -> InventoryKPI:
    where_fragment, params = _channel_store_inventory_clause(
        scope,
        channel_code=channel_code,
        store_code=store_code,
        inventory_basis=inventory_basis,
    )
    base_row = _query_one(
        f"""
        {_inventory_base_cte()}
        SELECT
            COALESCE(SUM(available_inventory_qty * unit_cost), 0) AS current_inventory_amount,
            COALESCE(SUM(available_inventory_qty), 0) AS current_inventory_qty,
            COUNT(DISTINCT CASE WHEN available_inventory_qty > 0 THEN product_code END) AS inventory_sku_count,
            COUNT(DISTINCT CASE WHEN COALESCE(NULLIF(TRIM(store_code), ''), '') <> '' THEN store_code END) AS store_count
        FROM inventory_base
        {where_fragment}
        """,
        [date_window.inventory_snapshot_date] + params,
    )
    inventory_qty = float(base_row.get("current_inventory_qty", 0) or 0)
    quarter_sales_qty = sum(float(row.get("quarter_sales_qty", 0) or 0) for row in rows)
    cumulative_sales_qty = sum(float(row.get("cumulative_sales_qty", 0) or 0) for row in rows)
    last_30_days_sales, sell_through_rate, inventory_days, sales_available = _sales_metrics(
        date_window.inventory_snapshot_date,
        scope=scope,
        channel_code=channel_code,
        store_code=store_code,
        inventory_qty=inventory_qty,
    )
    return InventoryKPI(
        current_inventory_amount=float(base_row.get("current_inventory_amount", 0) or 0),
        current_inventory_qty=inventory_qty,
        inventory_sku_count=int(base_row.get("inventory_sku_count", 0) or 0),
        warehouse_count=int(base_row.get("store_count", 0) or 0),
        store_warehouse_count=int(base_row.get("store_count", 0) or 0),
        last_30_days_sales=last_30_days_sales,
        sell_through_rate=sell_through_rate,
        inventory_days=inventory_days,
        quarter_sell_through_rate=_sell_through_rate(quarter_sales_qty, inventory_qty),
        cumulative_sell_through_rate=_sell_through_rate(cumulative_sales_qty, inventory_qty),
        sales_available=sales_available,
    )


def _build_category_summary_from_rows(rows: list[dict[str, Any]], scope: str | None = None) -> list[InventoryCategorySummary]:
    category_field = "big_category_name" if (scope or "women").strip().lower() == "women" else "category_name"
    grouped: dict[str, dict[str, float | str | None]] = {}
    total_inventory_amount = 0.0
    for row in rows:
        category_name = str(row.get(category_field, "") or "未分类")
        bucket = grouped.setdefault(
            category_name,
            {
                "category_name": category_name,
                "inventory_amount": 0.0,
                "inventory_qty": 0.0,
                "quarter_sales_qty": 0.0,
                "cumulative_sales_qty": 0.0,
            },
        )
        bucket["inventory_amount"] = float(bucket["inventory_amount"] or 0) + float(row.get("inventory_amount", 0) or 0)
        bucket["inventory_qty"] = float(bucket["inventory_qty"] or 0) + float(row.get("current_inventory_qty", 0) or 0)
        bucket["quarter_sales_qty"] = float(bucket["quarter_sales_qty"] or 0) + float(row.get("quarter_sales_qty", 0) or 0)
        bucket["cumulative_sales_qty"] = float(bucket["cumulative_sales_qty"] or 0) + float(row.get("cumulative_sales_qty", 0) or 0)
        total_inventory_amount += float(row.get("inventory_amount", 0) or 0)
    summaries: list[InventoryCategorySummary] = []
    for payload in grouped.values():
        inventory_qty = float(payload["inventory_qty"] or 0)
        quarter_sales_qty = float(payload["quarter_sales_qty"] or 0)
        cumulative_sales_qty = float(payload["cumulative_sales_qty"] or 0)
        inventory_amount = float(payload["inventory_amount"] or 0)
        summaries.append(
            InventoryCategorySummary(
                category_name=str(payload["category_name"]),
                inventory_amount=inventory_amount,
                inventory_qty=inventory_qty,
                quarter_sales_qty=quarter_sales_qty,
                cumulative_sales_qty=cumulative_sales_qty,
                quarter_sell_through_rate=_sell_through_rate(quarter_sales_qty, inventory_qty),
                cumulative_sell_through_rate=_sell_through_rate(cumulative_sales_qty, inventory_qty),
                contribution_rate=(inventory_amount / total_inventory_amount) if total_inventory_amount else 0.0,
            )
        )
    summaries.sort(key=lambda item: (item.inventory_amount, item.inventory_qty, item.category_name), reverse=True)
    return summaries


def _build_sellthrough_products(rows: list[dict[str, Any]], product_sort: str, limit: int = 20) -> list[InventorySellThroughProduct]:
    sorted_rows = sorted(rows, key=lambda row: _product_sort_key(row, product_sort), reverse=True)
    products: list[InventorySellThroughProduct] = []
    for index, row in enumerate(sorted_rows[:limit], start=1):
        payload = dict(row)
        payload.update(get_product_image(str(row.get("product_code", "") or "")))
        payload["rank"] = index
        products.append(InventorySellThroughProduct.from_query_row(payload))
    return products


def get_inventory_kpis(inventory_date: str, scope: str | None = None, channel_code: str | None = None, store_code: str | None = None, inventory_basis: str | None = None) -> InventoryKPI:
    date_window = _inventory_date_window(scope=scope, channel_code=channel_code, store_code=store_code)
    rows = _product_sellthrough_rows(
        date_window,
        scope=scope,
        inventory_basis=inventory_basis,
        channel_code=channel_code,
        store_code=store_code,
    )
    return _build_kpis_from_rows(
        date_window,
        rows,
        scope=scope,
        channel_code=channel_code,
        store_code=store_code,
        inventory_basis=inventory_basis,
    )


def get_inventory_top_products(inventory_date: str, scope: str | None = None, channel_code: str | None = None, store_code: str | None = None, inventory_basis: str | None = None, limit: int = 20) -> list[InventoryTopProduct]:
    where_fragment, params = _channel_store_inventory_clause(scope, channel_code=channel_code, store_code=store_code, inventory_basis=inventory_basis)
    rows = _query_all(
        f"""
        {_inventory_base_cte()}
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


def get_inventory_warehouse_ranking(inventory_date: str, scope: str | None = None, channel_code: str | None = None, store_code: str | None = None, inventory_basis: str | None = None, limit: int = 20) -> list[InventoryWarehouseSummary]:
    where_fragment, params = _channel_store_inventory_clause(scope, channel_code=channel_code, store_code=store_code, inventory_basis=inventory_basis)
    rows = _query_all(
        f"""
        {_inventory_base_cte()}
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
                    AND COALESCE(is_store_warehouse, 0) = 0
                    AND COALESCE(NULLIF(TRIM(mapped_store_code), ''), '') = ''
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


def get_inventory_store_ranking(inventory_date: str, scope: str | None = None, channel_code: str | None = None, store_code: str | None = None, inventory_basis: str | None = None, limit: int = 20) -> list[InventoryStoreSummary]:
    where_fragment, params = _channel_store_inventory_clause(scope, channel_code=channel_code, store_code=store_code, inventory_basis=inventory_basis)
    rows = _query_all(
        f"""
        {_inventory_base_cte()}
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


def get_inventory_region_summary(inventory_date: str, scope: str | None = None, channel_code: str | None = None, store_code: str | None = None, inventory_basis: str | None = None) -> list[InventoryRegionSummary]:
    where_fragment, params = _channel_store_inventory_clause(scope, channel_code=channel_code, store_code=store_code, inventory_basis=inventory_basis)
    total_row = _query_one(
        f"""
        {_inventory_base_cte()}
        SELECT COALESCE(SUM(available_inventory_qty * unit_cost), 0) AS inventory_amount
        FROM inventory_base
        {where_fragment}
        """,
        [inventory_date] + params,
    )
    total_amount = float(total_row.get("inventory_amount", 0) or 0)
    rows = _query_all(
        f"""
        {_inventory_base_cte()}
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


def get_inventory_category_summary(inventory_date: str, scope: str | None = None, channel_code: str | None = None, store_code: str | None = None, inventory_basis: str | None = None) -> list[InventoryCategorySummary]:
    date_window = _inventory_date_window(scope=scope, channel_code=channel_code, store_code=store_code)
    rows = _product_sellthrough_rows(
        date_window,
        scope=scope,
        inventory_basis=inventory_basis,
        channel_code=channel_code,
        store_code=store_code,
    )
    return _build_category_summary_from_rows(rows, scope=scope)


def _inventory_health_summary_sql(inventory_date: str, scope: str | None = None, channel_code: str | None = None, store_code: str | None = None, inventory_basis: str | None = None) -> tuple[str, list[Any]]:
    inventory_where_sql, inventory_params = _channel_store_inventory_clause(scope, channel_code=channel_code, store_code=store_code, inventory_basis=inventory_basis)
    sales_where_sql, sales_params = build_where_clause(_sales_filters(scope, channel_code=channel_code, store_code=store_code, inventory_date=inventory_date), core_only=False)
    sql = f"""
    {_inventory_base_cte(include_joined=True)},
    inventory_products AS (
        SELECT
            product_code,
            MAX(product_name) AS product_name,
            COALESCE(SUM(available_inventory_qty), 0) AS inventory_qty,
            COALESCE(SUM(available_inventory_qty * unit_cost), 0) AS inventory_amount
        FROM inventory_base
        {inventory_where_sql}
        GROUP BY product_code
    ),
    sales_30d AS (
        SELECT
            product_code,
            COALESCE(SUM(qty), 0) AS sales_qty,
            COUNT(*) AS sales_rows
        FROM joined
        {sales_where_sql}
        GROUP BY product_code
    ),
    product_health AS (
        SELECT
            i.product_code,
            i.inventory_qty,
            i.inventory_amount,
            COALESCE(s.sales_qty, 0) AS sales_qty,
            COALESCE(s.sales_rows, 0) AS sales_rows,
            CASE
                WHEN COALESCE(s.sales_rows, 0) = 0 THEN NULL
                WHEN COALESCE(s.sales_qty, 0) + i.inventory_qty > 0 THEN COALESCE(s.sales_qty, 0) * 1.0 / (COALESCE(s.sales_qty, 0) + i.inventory_qty)
                ELSE NULL
            END AS sell_through_rate
        FROM inventory_products i
        LEFT JOIN sales_30d s ON s.product_code = i.product_code
    )
    SELECT
        CASE
            WHEN COALESCE(sell_through_rate, 0) > 0.8 THEN 'healthy'
            WHEN COALESCE(sell_through_rate, 0) >= 0.5 THEN 'normal'
            WHEN COALESCE(sell_through_rate, 0) >= 0.2 THEN 'slow_moving'
            ELSE 'dead_stock'
        END AS health_key,
        CASE
            WHEN COALESCE(sell_through_rate, 0) > 0.8 THEN '高动销'
            WHEN COALESCE(sell_through_rate, 0) >= 0.5 THEN '正常动销'
            WHEN COALESCE(sell_through_rate, 0) >= 0.2 THEN '低动销'
            ELSE '近期无动销'
        END AS health_name,
        CASE
            WHEN COALESCE(sell_through_rate, 0) > 0.8 THEN 'success'
            WHEN COALESCE(sell_through_rate, 0) >= 0.5 THEN 'primary'
            WHEN COALESCE(sell_through_rate, 0) >= 0.2 THEN 'warning'
            ELSE 'danger'
        END AS color_class,
        COUNT(*) AS sku_count,
        COALESCE(SUM(inventory_qty), 0) AS inventory_qty,
        COALESCE(SUM(inventory_amount), 0) AS inventory_amount
    FROM product_health
    GROUP BY health_key, health_name, color_class
    ORDER BY CASE health_key WHEN 'healthy' THEN 1 WHEN 'normal' THEN 2 WHEN 'slow_moving' THEN 3 ELSE 4 END
    """
    return sql, [inventory_date] + inventory_params + sales_params


def _inventory_quantity_summary_sql(inventory_date: str, scope: str | None = None, channel_code: str | None = None, store_code: str | None = None, inventory_basis: str | None = None) -> tuple[str, list[Any]]:
    where_fragment, params = _channel_store_inventory_clause(scope, channel_code=channel_code, store_code=store_code, inventory_basis=inventory_basis)
    sql = f"""
    {_inventory_base_cte()}
    SELECT
        COALESCE(SUM(available_inventory_qty * unit_cost), 0) AS current_inventory_amount,
        COALESCE(SUM(available_inventory_qty), 0) AS current_inventory_qty,
        COUNT(DISTINCT CASE WHEN available_inventory_qty > 0 THEN product_code END) AS inventory_sku_count,
        COUNT(DISTINCT CASE WHEN COALESCE(NULLIF(TRIM(store_code), ''), '') <> '' THEN store_code END) AS store_count,
        COUNT(DISTINCT CASE WHEN COALESCE(is_store_warehouse, 0) = 1 THEN warehouse_code END) AS terminal_warehouse_count,
        COUNT(DISTINCT warehouse_code) AS all_warehouse_count
    FROM inventory_base
    {where_fragment}
    """
    return sql, [inventory_date] + params


def get_inventory_quantity_summary(inventory_date: str, scope: str | None = None, channel_code: str | None = None, store_code: str | None = None, inventory_basis: str | None = None) -> dict[str, Any]:
    sql, params = _inventory_quantity_summary_sql(inventory_date, scope=scope, channel_code=channel_code, store_code=store_code, inventory_basis=inventory_basis)
    return _query_one(sql, params)


def _inventory_quantity_summary_bundle_sql(inventory_date: str, scope: str | None = None, channel_code: str | None = None, store_code: str | None = None) -> tuple[str, list[Any]]:
    where_fragment, params = _channel_store_inventory_clause(scope, channel_code=channel_code, store_code=store_code, inventory_basis="all")
    sql = f"""
    {_inventory_base_cte()}
    SELECT
        COUNT(*) AS total_rows,
        COUNT(DISTINCT product_code) AS unique_products,
        COUNT(DISTINCT warehouse_code) AS unique_warehouses,
        COALESCE(SUM(available_inventory_qty * unit_cost), 0) AS all_inventory_amount,
        COALESCE(SUM(available_inventory_qty), 0) AS all_inventory_qty,
        COUNT(DISTINCT CASE WHEN COALESCE(is_store_warehouse, 0) = 1 THEN warehouse_code END) AS terminal_warehouse_count,
        COUNT(DISTINCT warehouse_code) AS all_warehouse_count,
        COALESCE(SUM(CASE WHEN COALESCE(is_store_warehouse, 0) = 1 THEN available_inventory_qty * unit_cost ELSE 0 END), 0) AS terminal_inventory_amount,
        COALESCE(SUM(CASE WHEN COALESCE(is_store_warehouse, 0) = 1 THEN available_inventory_qty ELSE 0 END), 0) AS terminal_inventory_qty
    FROM inventory_base
    {where_fragment}
    """
    return sql, [inventory_date] + params


def get_inventory_quantity_summary_bundle(inventory_date: str, scope: str | None = None, channel_code: str | None = None, store_code: str | None = None) -> dict[str, Any]:
    sql, params = _inventory_quantity_summary_bundle_sql(inventory_date, scope=scope, channel_code=channel_code, store_code=store_code)
    return _query_one(sql, params)


def get_inventory_health_summary(inventory_date: str, scope: str | None = None, channel_code: str | None = None, store_code: str | None = None, inventory_basis: str | None = None) -> list[InventoryHealthSummary]:
    sql, params = _inventory_health_summary_sql(inventory_date, scope=scope, channel_code=channel_code, store_code=store_code, inventory_basis=inventory_basis)
    rows = _query_all(sql, params)
    return [InventoryHealthSummary.from_query_row(row) for row in rows]


def get_inventory_channel_options(scope: str = "women", inventory_basis: str | None = None) -> list[InventoryChannelOption]:
    where_fragment, params = _channel_store_inventory_clause(scope, inventory_basis=inventory_basis)
    rows = _query_all(
        f"""
        {_inventory_base_cte()}
        SELECT
            COALESCE(NULLIF(TRIM(store_channel_code), ''), '') AS channel_code,
            COALESCE(NULLIF(TRIM(store_channel_name), ''), '未分渠道') AS channel_name,
            COUNT(DISTINCT CASE WHEN COALESCE(NULLIF(TRIM(mapped_store_code), ''), '') <> '' THEN COALESCE(NULLIF(TRIM(mapped_store_code), ''), '') END) AS store_count,
            COALESCE(SUM(available_inventory_qty), 0) AS inventory_qty,
            COALESCE(SUM(available_inventory_qty * unit_cost), 0) AS inventory_amount
        FROM inventory_base
        {where_fragment}
          AND COALESCE(NULLIF(TRIM(store_channel_code), ''), '') <> ''
        GROUP BY COALESCE(NULLIF(TRIM(store_channel_code), ''), ''), COALESCE(NULLIF(TRIM(store_channel_name), ''), '未分渠道')
        ORDER BY inventory_amount DESC, inventory_qty DESC, channel_name ASC
        """,
        [inventory_date := _latest_inventory_date()] + params,
    )
    return [InventoryChannelOption.from_query_row(row) for row in rows]


def get_inventory_store_options(channel_code: str, scope: str = "women", inventory_basis: str | None = None) -> list[InventoryStoreOption]:
    channel_code = (channel_code or "").strip()
    if not channel_code:
        return []
    where_fragment, params = _channel_store_inventory_clause(scope, channel_code=channel_code, inventory_basis=inventory_basis)
    rows = _query_all(
        f"""
        {_inventory_base_cte()}
        SELECT
            COALESCE(NULLIF(TRIM(store_code), ''), '') AS store_code,
            COALESCE(NULLIF(TRIM(store_name), ''), COALESCE(NULLIF(TRIM(mapped_store_name), ''), '未绑定门店')) AS store_name,
            COALESCE(NULLIF(TRIM(warehouse_code), ''), '') AS warehouse_code,
            COALESCE(SUM(available_inventory_qty), 0) AS inventory_qty,
            COALESCE(SUM(available_inventory_qty * unit_cost), 0) AS inventory_amount
        FROM inventory_base
        {where_fragment}
          AND COALESCE(NULLIF(TRIM(store_code), ''), '') <> ''
        GROUP BY store_code, store_name, warehouse_code
        ORDER BY inventory_amount DESC, inventory_qty DESC, store_name ASC
        """,
        [_latest_inventory_date()] + params,
    )
    return [InventoryStoreOption.from_query_row(row) for row in rows]


def get_inventory_analysis_context(scope: str | None = None, channel_code: str | None = None, store_code: str | None = None, inventory_basis: str | None = None, product_sort: str | None = None) -> InventoryAnalysisContext:
    selected_scope = (scope or "women").strip().lower() or "women"
    if selected_scope not in {"women", "all"}:
        selected_scope = "women"
    selected_inventory_basis = _normalize_inventory_basis(inventory_basis)
    selected_product_sort = _normalize_product_sort(product_sort)
    selected_channel_code = (channel_code or "").strip()
    selected_store_code = (store_code or "").strip()
    date_window = _inventory_date_window(scope=selected_scope, channel_code=selected_channel_code or None, store_code=selected_store_code or None)
    period = InventoryPeriod(
        inventory_date=date_window.inventory_snapshot_date,
        label=f"当前库存快照：{date_window.inventory_snapshot_date}",
        inventory_snapshot_date=date_window.inventory_snapshot_date,
        latest_sales_date=date_window.latest_sales_date,
        effective_sales_date=date_window.effective_sales_date,
        quarter_start_date=date_window.quarter_start_date,
    )
    channel_options = get_inventory_channel_options(scope=selected_scope, inventory_basis=selected_inventory_basis)
    selected_channel_name = next((item.channel_name for item in channel_options if item.channel_code == selected_channel_code), "")
    filter_warning = ""
    if selected_channel_code and not selected_channel_name:
        filter_warning = "所选渠道无可用库存数据，已忽略该渠道。"
        selected_channel_code = ""
    store_options = get_inventory_store_options(selected_channel_code, scope=selected_scope, inventory_basis=selected_inventory_basis) if selected_channel_code else []
    selected_store_name = next((item.store_name for item in store_options if item.store_code == selected_store_code), "")
    if selected_store_code and not selected_store_name:
        filter_warning = "所选门店不属于当前渠道，已忽略该门店。"
        selected_store_code = ""
    channel_filter = selected_channel_code if selected_channel_code else None
    store_filter = selected_store_code if selected_store_code else None
    product_metric_rows = _product_sellthrough_rows(
        date_window,
        scope=selected_scope,
        inventory_basis=selected_inventory_basis,
        channel_code=channel_filter,
        store_code=store_filter,
    )
    kpis = _build_kpis_from_rows(
        date_window,
        product_metric_rows,
        scope=selected_scope,
        channel_code=channel_filter,
        store_code=store_filter,
        inventory_basis=selected_inventory_basis,
    )
    top_products = get_inventory_top_products(period.inventory_date, scope=selected_scope, channel_code=channel_filter, store_code=store_filter, inventory_basis=selected_inventory_basis, limit=20)
    sellthrough_products = _build_sellthrough_products(product_metric_rows, selected_product_sort, limit=20)
    warehouse_ranking = get_inventory_warehouse_ranking(period.inventory_date, scope=selected_scope, channel_code=channel_filter, store_code=store_filter, inventory_basis=selected_inventory_basis, limit=20)
    store_ranking = get_inventory_store_ranking(period.inventory_date, scope=selected_scope, channel_code=channel_filter, store_code=store_filter, inventory_basis=selected_inventory_basis, limit=20)
    region_summary = get_inventory_region_summary(period.inventory_date, scope=selected_scope, channel_code=channel_filter, store_code=store_filter, inventory_basis=selected_inventory_basis)
    category_summary = _build_category_summary_from_rows(product_metric_rows, scope=selected_scope)
    health_summary = get_inventory_health_summary(period.inventory_date, scope=selected_scope, channel_code=channel_filter, store_code=store_filter, inventory_basis=selected_inventory_basis)
    return InventoryAnalysisContext(
        period=period,
        kpis=kpis,
        top_products=top_products,
        sellthrough_products=sellthrough_products,
        warehouse_ranking=warehouse_ranking,
        store_ranking=store_ranking,
        region_summary=region_summary,
        category_summary=category_summary,
        health_summary=health_summary,
        selected_scope=selected_scope,
        selected_inventory_basis=selected_inventory_basis,
        inventory_basis_label=_inventory_basis_label(selected_inventory_basis),
        selected_channel_code=selected_channel_code,
        selected_channel_name=selected_channel_name,
        selected_store_code=selected_store_code,
        selected_store_name=selected_store_name,
        selected_product_sort=selected_product_sort,
        channel_options=channel_options,
        store_options=store_options,
        data_quality_note="库存数据来源于 ERP 库存快照。部分渠道或门店未完整执行出入库流程，数据可能与实际库存存在偏差，请结合业务实际判断。",
        filter_warning=filter_warning,
    )