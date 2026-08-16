from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


def _as_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _as_int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _format_ratio(value: float | None) -> str:
    if value is None:
        return "--"
    return f"{value:.1%}"


@dataclass(slots=True)
class StorePeriod:
    latest_sale_date: str
    current_start_date: str
    current_end_date: str
    previous_start_date: str
    previous_end_date: str
    label: str
    comparison_label: str = ""

    @classmethod
    def from_query_row(cls, row: Mapping[str, Any]) -> "StorePeriod":
        return cls(
            latest_sale_date=str(row.get("latest_sale_date", "") or ""),
            current_start_date=str(row.get("current_start_date", "") or ""),
            current_end_date=str(row.get("current_end_date", "") or ""),
            previous_start_date=str(row.get("previous_start_date", "") or ""),
            previous_end_date=str(row.get("previous_end_date", "") or ""),
            label=str(row.get("label", "") or ""),
            comparison_label=str(row.get("comparison_label", "") or ""),
        )

    @property
    def window_days(self) -> int:
        return 30

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class StoreKPI:
    current_sales_amount: float = 0.0
    current_sales_qty: float = 0.0
    active_stores: int = 0
    inactive_stores: int = 0
    average_sales_per_store: float = 0.0
    average_daily_sales_amount: float = 0.0
    average_discount_rate: float = 0.0
    growth_rate: float | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["growth_rate_label"] = _format_ratio(self.growth_rate)
        return payload


@dataclass(slots=True)
class StoreRankingRow:
    rank: int
    store_code: str
    store_name: str
    region_name: str
    channel_code: str
    store_type_name: str
    current_rows: int = 0
    current_sales_qty: float = 0.0
    current_sales_amount: float = 0.0
    current_standard_amount: float = 0.0
    current_active_days: int = 0
    current_discount_rate: float | None = None
    prior_rows: int = 0
    prior_sales_qty: float = 0.0
    prior_sales_amount: float = 0.0
    prior_standard_amount: float = 0.0
    prior_active_days: int = 0
    prior_discount_rate: float | None = None
    growth_amount: float = 0.0
    growth_rate: float | None = None
    average_ticket_amount: float | None = None

    @classmethod
    def from_query_row(cls, row: Mapping[str, Any], rank: int = 0) -> "StoreRankingRow":
        return cls(
            rank=rank,
            store_code=str(row.get("store_code", "") or ""),
            store_name=str(row.get("store_name", "") or ""),
            region_name=str(row.get("region_name", "") or ""),
            channel_code=str(row.get("channel_code", "") or ""),
            store_type_name=str(row.get("store_type_name", "") or ""),
            current_rows=_as_int(row.get("current_rows")),
            current_sales_qty=_as_float(row.get("current_sales_qty")),
            current_sales_amount=_as_float(row.get("current_sales_amount")),
            current_standard_amount=_as_float(row.get("current_standard_amount")),
            current_active_days=_as_int(row.get("current_active_days")),
            current_discount_rate=(None if row.get("current_discount_rate") is None else _as_float(row.get("current_discount_rate"))),
            prior_rows=_as_int(row.get("prior_rows")),
            prior_sales_qty=_as_float(row.get("prior_sales_qty")),
            prior_sales_amount=_as_float(row.get("prior_sales_amount")),
            prior_standard_amount=_as_float(row.get("prior_standard_amount")),
            prior_active_days=_as_int(row.get("prior_active_days")),
            prior_discount_rate=(None if row.get("prior_discount_rate") is None else _as_float(row.get("prior_discount_rate"))),
            growth_amount=_as_float(row.get("growth_amount")),
            growth_rate=(None if row.get("growth_rate") is None else _as_float(row.get("growth_rate"))),
            average_ticket_amount=(None if row.get("average_ticket_amount") is None else _as_float(row.get("average_ticket_amount"))),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["growth_rate_label"] = _format_ratio(self.growth_rate)
        payload["current_discount_rate_label"] = _format_ratio(self.current_discount_rate)
        return payload


@dataclass(slots=True)
class StoreHealthSummary:
    label: str
    store_count: int = 0
    sales_amount: float = 0.0
    sales_qty: float = 0.0
    contribution_rate: float = 0.0
    average_growth_rate: float | None = None
    color_class: str = "secondary"
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["average_growth_rate_label"] = _format_ratio(self.average_growth_rate)
        payload["contribution_rate_label"] = _format_ratio(self.contribution_rate)
        return payload


@dataclass(slots=True)
class StoreTrendPlaceholder:
    title: str
    description: str
    note: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class StoreAnalysisContext:
    period: StorePeriod
    kpis: StoreKPI
    health_summary: list[StoreHealthSummary] = field(default_factory=list)
    top_stores: list[StoreRankingRow] = field(default_factory=list)
    bottom_stores: list[StoreRankingRow] = field(default_factory=list)
    trend_placeholder: StoreTrendPlaceholder | None = None
    selected_store_code: str = ""
    selected_store_name: str = ""
    selected_store_detail: StoreRankingRow | None = None
    data_quality_note: str = ""
    filter_warning: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "period": self.period.to_dict(),
            "kpis": self.kpis.to_dict(),
            "health_summary": [item.to_dict() for item in self.health_summary],
            "top_stores": [item.to_dict() for item in self.top_stores],
            "bottom_stores": [item.to_dict() for item in self.bottom_stores],
            "trend_placeholder": None if self.trend_placeholder is None else self.trend_placeholder.to_dict(),
            "selected_store_code": self.selected_store_code,
            "selected_store_name": self.selected_store_name,
            "selected_store_detail": None if self.selected_store_detail is None else self.selected_store_detail.to_dict(),
            "data_quality_note": self.data_quality_note,
            "filter_warning": self.filter_warning,
        }


def _build_kpis(rows: list[StoreRankingRow], period: StorePeriod) -> StoreKPI:
    current_sales_amount = sum(row.current_sales_amount for row in rows)
    current_sales_qty = sum(row.current_sales_qty for row in rows)
    current_rows = sum(row.current_rows for row in rows)
    current_standard_amount = sum(row.current_standard_amount for row in rows)
    prior_sales_amount = sum(row.prior_sales_amount for row in rows)
    active_stores = sum(1 for row in rows if row.current_rows > 0 or row.current_active_days > 0)
    inactive_stores = len(rows) - active_stores
    average_sales_per_store = current_sales_amount / active_stores if active_stores else 0.0
    average_daily_sales_amount = current_sales_amount / period.window_days if period.window_days else 0.0
    average_discount_rate = current_sales_amount / current_standard_amount if current_standard_amount else 0.0
    growth_rate = ((current_sales_amount - prior_sales_amount) / prior_sales_amount) if prior_sales_amount else None
    return StoreKPI(
        current_sales_amount=current_sales_amount,
        current_sales_qty=current_sales_qty,
        active_stores=active_stores,
        inactive_stores=inactive_stores,
        average_sales_per_store=average_sales_per_store,
        average_daily_sales_amount=average_daily_sales_amount,
        average_discount_rate=average_discount_rate,
        growth_rate=growth_rate,
    )


def _classify_store(row: StoreRankingRow) -> tuple[str, str, str]:
    if row.current_rows <= 0 and row.current_active_days <= 0:
        return "沉默门店", "secondary", "当前观察周期内未产生销售。"
    if row.prior_sales_amount <= 0:
        return "新增门店", "info", "当前周期有销售，但前一周期无可比基数。"
    if row.growth_rate is None:
        return "稳定门店", "primary", "销售表现平稳。"
    if row.growth_rate >= 0.15:
        return "增长门店", "success", "当前周期相较前一周期显著增长。"
    if row.growth_rate <= -0.15:
        return "下滑门店", "danger", "当前周期相较前一周期明显回落。"
    return "稳定门店", "warning", "当前周期销售波动较小。"


def _build_health_summary(rows: list[StoreRankingRow], total_sales_amount: float) -> list[StoreHealthSummary]:
    buckets: dict[str, dict[str, Any]] = {}
    for row in rows:
        label, color_class, description = _classify_store(row)
        bucket = buckets.setdefault(
            label,
            {
                "label": label,
                "store_count": 0,
                "sales_amount": 0.0,
                "sales_qty": 0.0,
                "growth_weight": 0.0,
                "growth_base": 0.0,
                "color_class": color_class,
                "description": description,
            },
        )
        bucket["store_count"] += 1
        bucket["sales_amount"] += row.current_sales_amount
        bucket["sales_qty"] += row.current_sales_qty
        if row.prior_sales_amount > 0 and row.growth_rate is not None:
            bucket["growth_weight"] += (row.current_sales_amount - row.prior_sales_amount)
            bucket["growth_base"] += row.prior_sales_amount

    ordered_labels = ["增长门店", "稳定门店", "下滑门店", "新增门店", "沉默门店"]
    summaries: list[StoreHealthSummary] = []
    for label in ordered_labels:
        bucket = buckets.get(label)
        if not bucket:
            continue
        average_growth_rate = None
        if bucket["growth_base"] > 0:
            average_growth_rate = bucket["growth_weight"] / bucket["growth_base"]
        summaries.append(
            StoreHealthSummary(
                label=str(bucket["label"]),
                store_count=_as_int(bucket["store_count"]),
                sales_amount=_as_float(bucket["sales_amount"]),
                sales_qty=_as_float(bucket["sales_qty"]),
                contribution_rate=(_as_float(bucket["sales_amount"]) / total_sales_amount) if total_sales_amount else 0.0,
                average_growth_rate=average_growth_rate,
                color_class=str(bucket["color_class"]),
                description=str(bucket["description"]),
            )
        )
    return summaries


def build_store_analysis_context(raw: Mapping[str, Any]) -> StoreAnalysisContext:
    period = StorePeriod.from_query_row(raw.get("period", {}))
    ranking_rows = [StoreRankingRow.from_query_row(row, rank=index) for index, row in enumerate(raw.get("store_rows", []), start=1)]
    kpis = _build_kpis(ranking_rows, period)
    health_summary = _build_health_summary(ranking_rows, kpis.current_sales_amount)
    top_stores = ranking_rows[:20]
    bottom_source = sorted(ranking_rows, key=lambda row: (row.current_sales_amount, row.current_sales_qty, row.store_name, row.store_code))
    bottom_stores = [StoreRankingRow.from_query_row(asdict(row), rank=index) for index, row in enumerate(bottom_source[:20], start=1)]
    selected_store_code = str(raw.get("selected_store_code", "") or "")
    selected_store_detail = next((row for row in ranking_rows if row.store_code == selected_store_code), None)
    selected_store_name = selected_store_detail.store_name if selected_store_detail else ""
    filter_warning = ""
    if selected_store_code and not selected_store_detail:
        filter_warning = "未找到对应门店编码，请检查输入后重试。"
    return StoreAnalysisContext(
        period=period,
        kpis=kpis,
        health_summary=health_summary,
        top_stores=top_stores,
        bottom_stores=bottom_stores,
        trend_placeholder=StoreTrendPlaceholder(
            title="趋势看板预留",
            description="后续可在此接入门店日度销售折线、排名变化和区域联动筛选。",
            note="当前版本保留为只读入口，便于后续扩展。",
        ),
        selected_store_code=selected_store_code,
        selected_store_name=selected_store_name,
        selected_store_detail=selected_store_detail,
        data_quality_note="门店分析直接基于 fact_retail_sales 聚合，不依赖库存或商品表。门店编码未映射时将以原始编码展示。",
        filter_warning=filter_warning,
    )