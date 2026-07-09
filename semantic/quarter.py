from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


QUARTER_MONTHS = {
    1: (1, 2, 3),
    2: (4, 5, 6),
    3: (7, 8, 9),
    4: (10, 11, 12),
}

QUARTER_LABELS = {
    1: "第一季度",
    2: "第二季度",
    3: "第三季度",
    4: "第四季度",
}


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


@dataclass(slots=True)
class QuarterPeriod:
    selected_year: int
    selected_quarter: int
    start_date: str
    end_date: str
    label: str

    @classmethod
    def from_query_row(cls, row: Mapping[str, Any]) -> "QuarterPeriod":
        return cls(
            selected_year=_as_int(row.get("selected_year")),
            selected_quarter=_as_int(row.get("selected_quarter")),
            start_date=str(row.get("start_date", "") or ""),
            end_date=str(row.get("end_date", "") or ""),
            label=str(row.get("label", "") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class QuarterKPI:
    sales_amount: float = 0.0
    sales_qty: float = 0.0
    active_stores: int = 0
    active_products: int = 0
    average_discount_rate: float = 0.0

    @classmethod
    def from_query_row(cls, row: Mapping[str, Any]) -> "QuarterKPI":
        return cls(
            sales_amount=_as_float(row.get("sales_amount")),
            sales_qty=_as_float(row.get("sales_qty")),
            active_stores=_as_int(row.get("active_stores")),
            active_products=_as_int(row.get("active_products")),
            average_discount_rate=_as_float(row.get("average_discount_rate")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class QuarterComparison:
    label: str
    sales_amount_change: float | None = None
    sales_qty_change: float | None = None
    active_products_change: float | None = None
    average_discount_change: float | None = None
    sales_amount_delta: float | None = None
    sales_qty_delta: float | None = None
    active_products_delta: float | None = None
    average_discount_delta: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class QuarterTopProduct:
    rank: int
    product_code: str
    product_name: str
    image_url: str = ""
    sales_amount: float = 0.0
    sales_qty: float = 0.0
    active_stores: int = 0
    average_unit_price: float = 0.0
    average_discount_rate: float = 0.0

    @classmethod
    def from_query_row(cls, row: Mapping[str, Any]) -> "QuarterTopProduct":
        return cls(
            rank=_as_int(row.get("rank")),
            product_code=str(row.get("product_code", "") or ""),
            product_name=str(row.get("product_name", "") or ""),
            image_url=str(row.get("image_url", "") or ""),
            sales_amount=_as_float(row.get("sales_amount")),
            sales_qty=_as_float(row.get("sales_qty")),
            active_stores=_as_int(row.get("active_stores")),
            average_unit_price=_as_float(row.get("average_unit_price")),
            average_discount_rate=_as_float(row.get("average_discount_rate")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class QuarterRegionSummary:
    region_name: str
    sales_amount: float = 0.0
    sales_qty: float = 0.0
    contribution_rate: float = 0.0
    comparison_text: str = ""

    @classmethod
    def from_query_row(cls, row: Mapping[str, Any]) -> "QuarterRegionSummary":
        return cls(
            region_name=str(row.get("region_name", "") or ""),
            sales_amount=_as_float(row.get("sales_amount")),
            sales_qty=_as_float(row.get("sales_qty")),
            contribution_rate=_as_float(row.get("contribution_rate")),
            comparison_text=str(row.get("comparison_text", "") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class QuarterCategorySummary:
    category_name: str
    sales_amount: float = 0.0
    sales_qty: float = 0.0
    contribution_rate: float = 0.0

    @classmethod
    def from_query_row(cls, row: Mapping[str, Any]) -> "QuarterCategorySummary":
        return cls(
            category_name=str(row.get("category_name", "") or ""),
            sales_amount=_as_float(row.get("sales_amount")),
            sales_qty=_as_float(row.get("sales_qty")),
            contribution_rate=_as_float(row.get("contribution_rate")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class QuarterWaveSummary:
    wave_name: str
    sales_amount: float = 0.0
    sales_qty: float = 0.0
    contribution_rate: float = 0.0

    @classmethod
    def from_query_row(cls, row: Mapping[str, Any]) -> "QuarterWaveSummary":
        return cls(
            wave_name=str(row.get("wave_name", "") or ""),
            sales_amount=_as_float(row.get("sales_amount")),
            sales_qty=_as_float(row.get("sales_qty")),
            contribution_rate=_as_float(row.get("contribution_rate")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class QuarterAnalysisContext:
    period: QuarterPeriod
    kpis: QuarterKPI
    comparisons: list[QuarterComparison] = field(default_factory=list)
    top_products: list[QuarterTopProduct] = field(default_factory=list)
    region_summary: list[QuarterRegionSummary] = field(default_factory=list)
    category_summary: list[QuarterCategorySummary] = field(default_factory=list)
    wave_summary: list[QuarterWaveSummary] = field(default_factory=list)
    available_years: list[int] = field(default_factory=list)
    available_quarters: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "period": self.period.to_dict(),
            "kpis": self.kpis.to_dict(),
            "comparisons": [item.to_dict() for item in self.comparisons],
            "top_products": [item.to_dict() for item in self.top_products],
            "region_summary": [item.to_dict() for item in self.region_summary],
            "category_summary": [item.to_dict() for item in self.category_summary],
            "wave_summary": [item.to_dict() for item in self.wave_summary],
            "available_years": list(self.available_years),
            "available_quarters": list(self.available_quarters),
        }
