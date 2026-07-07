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


@dataclass(slots=True)
class ProductDetailProfile:
    product_code: str
    product_name: str
    image_path: str
    image_url: str
    has_image: bool
    year: Any
    season_name: str
    wave: str
    designer_name: str
    category_name: str
    big_category_name: str
    brand_name: str = ""
    series_name: str = ""

    @classmethod
    def from_query_row(cls, row: Mapping[str, Any]) -> "ProductDetailProfile":
        return cls(
            product_code=str(row.get("product_code", "") or ""),
            product_name=str(row.get("product_name", "") or ""),
            image_path=str(row.get("image_path", "") or ""),
            image_url=str(row.get("image_url", "") or ""),
            has_image=bool(row.get("has_image", False)),
            year=row.get("year"),
            season_name=str(row.get("season_name", "") or ""),
            wave=str(row.get("wave", "") or ""),
            designer_name=str(row.get("designer_name", "") or ""),
            category_name=str(row.get("category_name", "") or ""),
            big_category_name=str(row.get("big_category_name", "") or ""),
            brand_name=str(row.get("brand_name", "") or ""),
            series_name=str(row.get("series_name", "") or ""),
        )


@dataclass(slots=True)
class ProductSalesSummary:
    sales_qty: float = 0.0
    sales_amount: float = 0.0
    standard_amount: float = 0.0
    average_unit_price: float = 0.0
    average_standard_price: float = 0.0
    average_discount_rate: float = 0.0
    transaction_count: int = 0
    store_count: int = 0
    color_count: int = 0
    size_count: int = 0

    @classmethod
    def from_query_row(cls, row: Mapping[str, Any]) -> "ProductSalesSummary":
        return cls(
            sales_qty=_as_float(row.get("sales_qty")),
            sales_amount=_as_float(row.get("sales_amount")),
            standard_amount=_as_float(row.get("standard_amount")),
            average_unit_price=_as_float(row.get("average_unit_price")),
            average_standard_price=_as_float(row.get("average_standard_price")),
            average_discount_rate=_as_float(row.get("average_discount_rate")),
            transaction_count=_as_int(row.get("transaction_count")),
            store_count=_as_int(row.get("store_count")),
            color_count=_as_int(row.get("color_count")),
            size_count=_as_int(row.get("size_count")),
        )


@dataclass(slots=True)
class ProductTrend:
    points: list[dict[str, Any]] = field(default_factory=list)
    total_points: int = 0
    first_date: str = ""
    last_date: str = ""
    peak_amount: float = 0.0

    @classmethod
    def from_query_rows(cls, rows: list[Mapping[str, Any]]) -> "ProductTrend":
        points = [dict(row) for row in rows]
        first_date = str(points[0].get("sale_date", "")) if points else ""
        last_date = str(points[-1].get("sale_date", "")) if points else ""
        peak_amount = max((_as_float(row.get("sales_amount")) for row in points), default=0.0)
        return cls(points=points, total_points=len(points), first_date=first_date, last_date=last_date, peak_amount=peak_amount)


@dataclass(slots=True)
class ProductRegionSummary:
    regions: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_query_rows(cls, rows: list[Mapping[str, Any]]) -> "ProductRegionSummary":
        return cls(regions=[dict(row) for row in rows])


@dataclass(slots=True)
class ProductStoreSummary:
    stores: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_query_rows(cls, rows: list[Mapping[str, Any]]) -> "ProductStoreSummary":
        return cls(stores=[dict(row) for row in rows])


@dataclass(slots=True)
class ProductColorSummary:
    colors: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_query_rows(cls, rows: list[Mapping[str, Any]]) -> "ProductColorSummary":
        return cls(colors=[dict(row) for row in rows])


@dataclass(slots=True)
class ProductSizeSummary:
    sizes: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_query_rows(cls, rows: list[Mapping[str, Any]]) -> "ProductSizeSummary":
        return cls(sizes=[dict(row) for row in rows])


@dataclass(slots=True)
class ProductAIContext:
    profile: ProductDetailProfile
    sales_summary: ProductSalesSummary
    trend_summary: ProductTrend
    region_summary: ProductRegionSummary
    store_summary: ProductStoreSummary
    color_summary: ProductColorSummary
    size_summary: ProductSizeSummary
    latest_activity: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": asdict(self.profile),
            "sales_summary": asdict(self.sales_summary),
            "trend_summary": asdict(self.trend_summary),
            "region_summary": asdict(self.region_summary),
            "store_summary": asdict(self.store_summary),
            "color_summary": asdict(self.color_summary),
            "size_summary": asdict(self.size_summary),
            "latest_activity": list(self.latest_activity),
        }


@dataclass(slots=True)
class ProductDetail:
    profile: ProductDetailProfile
    sales_summary: ProductSalesSummary
    trend: ProductTrend
    region_summary: ProductRegionSummary
    store_summary: ProductStoreSummary
    color_summary: ProductColorSummary
    size_summary: ProductSizeSummary
    ai_context: ProductAIContext
