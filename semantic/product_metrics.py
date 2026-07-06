from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(slots=True)
class ProductPerformance:
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
    standard_price: float
    sales_qty: float
    sales_amount: float
    average_unit_price: float
    store_coverage: int
    color_count: int
    size_count: int

    @classmethod
    def from_query_row(cls, row: Mapping[str, Any]) -> "ProductPerformance":
        sales_qty = float(row.get("qty", 0) or 0)
        sales_amount = float(row.get("amount", 0) or 0)
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
            standard_price=float(row.get("standard_price", 0) or 0),
            sales_qty=sales_qty,
            sales_amount=sales_amount,
            average_unit_price=(sales_amount / sales_qty) if sales_qty else 0.0,
            store_coverage=int(row.get("store_count", 0) or 0),
            color_count=int(row.get("color_count", 0) or 0),
            size_count=int(row.get("size_count", 0) or 0),
        )

    @property
    def qty(self) -> float:
        return self.sales_qty

    @property
    def amount(self) -> float:
        return self.sales_amount

    @property
    def store_count(self) -> int:
        return self.store_coverage
