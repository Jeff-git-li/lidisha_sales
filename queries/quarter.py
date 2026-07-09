from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from assets.asset_service import get_product_image
from queries.filters import build_where_clause
from queries.retail_queries import JOINED_CTE, _query_all, _query_one
from semantic.quarter import (
    QUARTER_LABELS,
    QUARTER_MONTHS,
    QuarterAnalysisContext,
    QuarterCategorySummary,
    QuarterComparison,
    QuarterKPI,
    QuarterPeriod,
    QuarterRegionSummary,
    QuarterTopProduct,
    QuarterWaveSummary,
)


@dataclass(slots=True)
class QuarterBoundary:
    selected_year: int
    selected_quarter: int
    start_date: str
    end_date: str

    def to_period(self) -> QuarterPeriod:
        return QuarterPeriod(
            selected_year=self.selected_year,
            selected_quarter=self.selected_quarter,
            start_date=self.start_date,
            end_date=self.end_date,
            label=f"{self.selected_year}年Q{self.selected_quarter}（{QUARTER_LABELS[self.selected_quarter]}）",
        )


def _quarter_from_month(month: int) -> int:
    if month in (1, 2, 3):
        return 1
    if month in (4, 5, 6):
        return 2
    if month in (7, 8, 9):
        return 3
    return 4


def _month_range_for_quarter(year: int, quarter: int) -> tuple[str, str]:
    months = QUARTER_MONTHS[quarter]
    start = date(year, months[0], 1)
    if months[2] == 12:
        end = date(year, 12, 31)
    else:
        next_month = date(year, months[2] + 1, 1)
        end = next_month.replace(day=1) - date.resolution
    return start.isoformat(), end.isoformat()


def _latest_sale_date() -> str:
    row = _query_one(
        f"""
        {JOINED_CTE}
        SELECT COALESCE(MAX(sale_date), '') AS latest_sale_date
        FROM joined
        WHERE COALESCE(NULLIF(TRIM(year), ''), '') <> ''
          AND COALESCE(NULLIF(TRIM(season_name), ''), '') <> ''
        """
    )
    return str(row.get("latest_sale_date", "") or "")


def _latest_boundary() -> QuarterBoundary | None:
    latest_sale_date = _latest_sale_date()
    if not latest_sale_date:
        return None
    selected_year = int(latest_sale_date[:4])
    selected_quarter = _quarter_from_month(int(latest_sale_date[5:7]))
    start_date, end_date = _month_range_for_quarter(selected_year, selected_quarter)
    return QuarterBoundary(
        selected_year=selected_year,
        selected_quarter=selected_quarter,
        start_date=start_date,
        end_date=end_date,
    )


def get_available_quarters() -> dict[str, Any]:
    rows = _query_all(
        f"""
        {JOINED_CTE}
        SELECT DISTINCT
            CAST(substr(sale_date, 1, 4) AS INTEGER) AS selected_year,
            CASE
                WHEN CAST(substr(sale_date, 6, 2) AS INTEGER) IN (1, 2, 3) THEN 1
                WHEN CAST(substr(sale_date, 6, 2) AS INTEGER) IN (4, 5, 6) THEN 2
                WHEN CAST(substr(sale_date, 6, 2) AS INTEGER) IN (7, 8, 9) THEN 3
                ELSE 4
            END AS selected_quarter
        FROM joined
        WHERE COALESCE(NULLIF(TRIM(year), ''), '') <> ''
          AND COALESCE(NULLIF(TRIM(season_name), ''), '') <> ''
        ORDER BY selected_year DESC, selected_quarter DESC
        """
    )
    years = []
    quarters: list[dict[str, Any]] = []
    for row in rows:
        year = int(row.get("selected_year") or 0)
        quarter = int(row.get("selected_quarter") or 0)
        if year and year not in years:
            years.append(year)
        if year and quarter:
            quarters.append({"selected_year": year, "selected_quarter": quarter, "label": f"{year}年Q{quarter}"})
    return {"available_years": years, "available_quarters": quarters}


def get_quarter_period(selected_year: int | str | None = None, selected_quarter: int | str | None = None) -> QuarterPeriod:
    if selected_year and selected_quarter:
        year = int(selected_year)
        quarter = int(selected_quarter)
        start_date, end_date = _month_range_for_quarter(year, quarter)
        return QuarterPeriod(
            selected_year=year,
            selected_quarter=quarter,
            start_date=start_date,
            end_date=end_date,
            label=f"{year}年Q{quarter}（{QUARTER_LABELS[quarter]}）",
        )

    latest = _latest_boundary()
    if latest:
        return latest.to_period()

    today = date.today()
    quarter = _quarter_from_month(today.month)
    start_date, end_date = _month_range_for_quarter(today.year, quarter)
    return QuarterPeriod(
        selected_year=today.year,
        selected_quarter=quarter,
        start_date=start_date,
        end_date=end_date,
        label=f"{today.year}年Q{quarter}（{QUARTER_LABELS[quarter]}）",
    )


def _quarter_filter(period: QuarterPeriod, scope: str | None = None) -> dict[str, list[str]]:
    return {
        "start_date": [period.start_date],
        "end_date": [period.end_date],
        "scope": [scope or "women"],
    }


def get_quarter_kpis(period: QuarterPeriod, scope: str | None = None) -> QuarterKPI:
    where_sql, params = build_where_clause(_quarter_filter(period, scope), core_only=True)
    sql = f"""
    {JOINED_CTE}
    SELECT
        COALESCE(SUM(qty), 0) AS sales_qty,
        COALESCE(SUM(effective_amount), 0) AS sales_amount,
        COUNT(DISTINCT store_code) AS active_stores,
        COUNT(DISTINCT product_code) AS active_products,
        CASE
            WHEN COALESCE(SUM(standard_amount), 0) > 0 THEN SUM(amount) * 1.0 / SUM(standard_amount)
            ELSE NULL
        END AS average_discount_rate
    FROM joined
    {where_sql}
    """
    row = _query_one(sql, params)
    return QuarterKPI.from_query_row({
        "sales_qty": row.get("sales_qty", 0),
        "sales_amount": row.get("sales_amount", 0),
        "active_stores": row.get("active_stores", 0),
        "active_products": row.get("active_products", 0),
        "average_discount_rate": row.get("average_discount_rate", 0),
    })


def _compare_value(current: float | int | None, previous: float | int | None) -> float | None:
    if previous in (None, 0):
        return None
    if current is None:
        return None
    return (float(current) - float(previous)) / float(previous)


def get_quarter_comparison(period: QuarterPeriod, compare_period: QuarterPeriod, scope: str | None = None) -> QuarterComparison:
    current = get_quarter_kpis(period, scope=scope)
    previous = get_quarter_kpis(compare_period, scope=scope)
    return QuarterComparison(
        label=compare_period.label,
        sales_amount_change=_compare_value(current.sales_amount, previous.sales_amount),
        sales_qty_change=_compare_value(current.sales_qty, previous.sales_qty),
        active_products_change=_compare_value(current.active_products, previous.active_products),
        average_discount_change=_compare_value(current.average_discount_rate, previous.average_discount_rate),
        sales_amount_delta=float(current.sales_amount) - float(previous.sales_amount),
        sales_qty_delta=float(current.sales_qty) - float(previous.sales_qty),
        active_products_delta=float(current.active_products) - float(previous.active_products),
        average_discount_delta=float(current.average_discount_rate) - float(previous.average_discount_rate),
    )


def get_quarter_top_products(period: QuarterPeriod, limit: int = 20, sort_by: str = "amount", scope: str | None = None) -> list[QuarterTopProduct]:
    where_sql, params = build_where_clause(_quarter_filter(period, scope), core_only=True)
    order_sql = "sales_amount DESC, sales_qty DESC, product_code ASC"
    if sort_by == "qty":
        order_sql = "sales_qty DESC, sales_amount DESC, product_code ASC"
    sql = f"""
    {JOINED_CTE}
    SELECT
        product_code,
        MAX(product_name) AS product_name,
        MAX(color_code) AS color_code,
        MAX(color_name) AS color_name,
        MAX(standard_price) AS standard_price,
        COALESCE(SUM(qty), 0) AS sales_qty,
        COALESCE(SUM(effective_amount), 0) AS sales_amount,
        COUNT(DISTINCT store_code) AS active_stores,
        CASE WHEN COALESCE(SUM(qty), 0) = 0 THEN 0 ELSE COALESCE(SUM(effective_amount), 0) / COALESCE(SUM(qty), 1) END AS average_unit_price,
        CASE WHEN COALESCE(SUM(standard_amount), 0) > 0 THEN SUM(amount) * 1.0 / SUM(standard_amount) ELSE NULL END AS average_discount_rate
    FROM joined
    {where_sql}
    GROUP BY product_code
    ORDER BY {order_sql}
    LIMIT ?
    """
    rows = _query_all(sql, params + [int(limit)])
    products: list[QuarterTopProduct] = []
    for index, row in enumerate(rows, start=1):
        image = get_product_image(str(row.get("product_code", "") or ""), row.get("color_code"))
        payload = dict(row)
        payload.update(image)
        payload["rank"] = index
        products.append(QuarterTopProduct.from_query_row(payload))
    return products


def get_quarter_region_summary(period: QuarterPeriod, scope: str | None = None) -> list[QuarterRegionSummary]:
    where_sql, params = build_where_clause(_quarter_filter(period, scope), core_only=True)
    total_row = _query_one(
        f"""
        {JOINED_CTE}
        SELECT COALESCE(SUM(qty), 0) AS sales_qty, COALESCE(SUM(effective_amount), 0) AS sales_amount
        FROM joined
        {where_sql}
        """,
        params,
    )
    total_amount = float(total_row.get("sales_amount", 0) or 0)
    sql = f"""
    {JOINED_CTE}
    SELECT
        COALESCE(region_name, '未分区') AS region_name,
        COALESCE(SUM(qty), 0) AS sales_qty,
        COALESCE(SUM(effective_amount), 0) AS sales_amount
    FROM joined
    {where_sql}
    GROUP BY COALESCE(region_name, '未分区')
    ORDER BY sales_amount DESC, sales_qty DESC, region_name ASC
    """
    rows = _query_all(sql, params)
    previous_period = _previous_quarter(period)
    previous_regions = _region_amount_map(previous_period) if previous_period else {}
    summaries: list[QuarterRegionSummary] = []
    for row in rows:
        region_name = str(row.get("region_name", "") or "未分区")
        current_amount = float(row.get("sales_amount", 0) or 0)
        previous_amount = previous_regions.get(region_name)
        comparison_text = _comparison_text(current_amount, previous_amount)
        contribution = (current_amount / total_amount) if total_amount else 0.0
        summaries.append(
            QuarterRegionSummary(
                region_name=region_name,
                sales_amount=current_amount,
                sales_qty=float(row.get("sales_qty", 0) or 0),
                contribution_rate=contribution,
                comparison_text=comparison_text,
            )
        )
    return summaries


def _region_amount_map(period: QuarterPeriod, scope: str | None = None) -> dict[str, float]:
    where_sql, params = build_where_clause(_quarter_filter(period, scope), core_only=True)
    sql = f"""
    {JOINED_CTE}
    SELECT COALESCE(region_name, '未分区') AS region_name, COALESCE(SUM(effective_amount), 0) AS sales_amount
    FROM joined
    {where_sql}
    GROUP BY COALESCE(region_name, '未分区')
    """
    rows = _query_all(sql, params)
    return {str(row.get("region_name", "") or "未分区"): float(row.get("sales_amount", 0) or 0) for row in rows}


def get_quarter_category_summary(period: QuarterPeriod, scope: str | None = None) -> list[QuarterCategorySummary]:
    where_sql, params = build_where_clause(_quarter_filter(period, scope), core_only=True)
    total_row = _query_one(
        f"""
        {JOINED_CTE}
        SELECT COALESCE(SUM(effective_amount), 0) AS sales_amount
        FROM joined
        {where_sql}
        """,
        params,
    )
    total_amount = float(total_row.get("sales_amount", 0) or 0)
    rows = _query_all(
        f"""
        {JOINED_CTE}
        SELECT
            COALESCE(category_name, '未分类') AS category_name,
            COALESCE(SUM(qty), 0) AS sales_qty,
            COALESCE(SUM(effective_amount), 0) AS sales_amount
        FROM joined
        {where_sql}
        GROUP BY COALESCE(category_name, '未分类')
        ORDER BY sales_amount DESC, sales_qty DESC, category_name ASC
        """,
        params,
    )
    return [
        QuarterCategorySummary(
            category_name=str(row.get("category_name", "") or "未分类"),
            sales_amount=float(row.get("sales_amount", 0) or 0),
            sales_qty=float(row.get("sales_qty", 0) or 0),
            contribution_rate=(float(row.get("sales_amount", 0) or 0) / total_amount) if total_amount else 0.0,
        )
        for row in rows
    ]


def get_quarter_wave_summary(period: QuarterPeriod, scope: str | None = None) -> list[QuarterWaveSummary]:
    where_sql, params = build_where_clause(_quarter_filter(period, scope), core_only=True)
    total_row = _query_one(
        f"""
        {JOINED_CTE}
        SELECT COALESCE(SUM(effective_amount), 0) AS sales_amount
        FROM joined
        {where_sql}
        """,
        params,
    )
    total_amount = float(total_row.get("sales_amount", 0) or 0)
    rows = _query_all(
        f"""
        {JOINED_CTE}
        SELECT
            COALESCE(wave, '未识别') AS wave_name,
            COALESCE(SUM(qty), 0) AS sales_qty,
            COALESCE(SUM(effective_amount), 0) AS sales_amount
        FROM joined
        {where_sql}
        GROUP BY COALESCE(wave, '未识别')
        ORDER BY sales_amount DESC, sales_qty DESC, wave_name ASC
        """,
        params,
    )
    return [
        QuarterWaveSummary(
            wave_name=str(row.get("wave_name", "") or "未识别"),
            sales_amount=float(row.get("sales_amount", 0) or 0),
            sales_qty=float(row.get("sales_qty", 0) or 0),
            contribution_rate=(float(row.get("sales_amount", 0) or 0) / total_amount) if total_amount else 0.0,
        )
        for row in rows
    ]


def _previous_quarter(period: QuarterPeriod) -> QuarterPeriod | None:
    year = period.selected_year
    quarter = period.selected_quarter - 1
    if quarter == 0:
        year -= 1
        quarter = 4
    if year <= 0:
        return None
    start_date, end_date = _month_range_for_quarter(year, quarter)
    return QuarterPeriod(
        selected_year=year,
        selected_quarter=quarter,
        start_date=start_date,
        end_date=end_date,
        label=f"{year}年Q{quarter}（{QUARTER_LABELS[quarter]}）",
    )


def _same_quarter_last_year(period: QuarterPeriod) -> QuarterPeriod | None:
    year = period.selected_year - 1
    if year <= 0:
        return None
    start_date, end_date = _month_range_for_quarter(year, period.selected_quarter)
    return QuarterPeriod(
        selected_year=year,
        selected_quarter=period.selected_quarter,
        start_date=start_date,
        end_date=end_date,
        label=f"{year}年Q{period.selected_quarter}（{QUARTER_LABELS[period.selected_quarter]}）",
    )


def _comparison_text(current: float | None, previous: float | None) -> str:
    if previous in (None, 0):
        return "暂无对比数据"
    if current is None:
        return "暂无对比数据"
    delta = (float(current) - float(previous)) / float(previous)
    direction = "增长" if delta >= 0 else "下降"
    return f"较上期{direction}{abs(delta):.1%}"


def get_quarter_analysis_context(selected_year: int | None = None, selected_quarter: int | None = None, scope: str | None = None) -> QuarterAnalysisContext:
    period = get_quarter_period(selected_year, selected_quarter)
    availability = get_available_quarters()
    kpis = get_quarter_kpis(period, scope=scope)
    comparisons: list[QuarterComparison] = []
    previous = _previous_quarter(period)
    same_last_year = _same_quarter_last_year(period)
    if previous:
        comparisons.append(get_quarter_comparison(period, previous, scope=scope))
    if same_last_year:
        comparisons.append(get_quarter_comparison(period, same_last_year, scope=scope))
    top_products = get_quarter_top_products(period, limit=20, sort_by="amount", scope=scope)
    region_summary = get_quarter_region_summary(period, scope=scope)
    category_summary = get_quarter_category_summary(period, scope=scope)
    wave_summary = get_quarter_wave_summary(period, scope=scope)
    return QuarterAnalysisContext(
        period=period,
        kpis=kpis,
        comparisons=comparisons,
        top_products=top_products,
        region_summary=region_summary,
        category_summary=category_summary,
        wave_summary=wave_summary,
        available_years=availability["available_years"],
        available_quarters=availability["available_quarters"],
    )
