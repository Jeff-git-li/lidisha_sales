from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from semantic.product_detail import ProductDetail


def _format_number(value: Any, digits: int = 2) -> str:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        number = 0.0
    if digits == 0:
        return f"{number:,.0f}"
    return f"{number:,.{digits}f}"


def _normalize_rows(rows: list[Mapping[str, Any]], limit: int) -> list[dict[str, Any]]:
    return [dict(row) for row in rows[:limit]]


@dataclass(slots=True)
class ProductAIContext:
    profile: Any
    sales_summary: Any
    trend_summary: Any
    top_colors: list[dict[str, Any]] = field(default_factory=list)
    top_sizes: list[dict[str, Any]] = field(default_factory=list)
    top_regions: list[dict[str, Any]] = field(default_factory=list)
    top_stores: list[dict[str, Any]] = field(default_factory=list)
    discount_summary: dict[str, Any] = field(default_factory=dict)
    latest_activity: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_product_detail(cls, detail: ProductDetail, top_n: int = 5) -> "ProductAIContext":
        sales_summary = detail.sales_summary
        discount_amount = max(float(getattr(sales_summary, "standard_amount", 0) or 0) - float(getattr(sales_summary, "sales_amount", 0) or 0), 0.0)
        standard_amount = float(getattr(sales_summary, "standard_amount", 0) or 0)
        sales_amount = float(getattr(sales_summary, "sales_amount", 0) or 0)
        discount_rate = sales_amount / standard_amount if standard_amount else 0.0
        discount_summary = {
            "standard_amount": standard_amount,
            "sales_amount": sales_amount,
            "discount_amount": discount_amount,
            "average_discount_rate": discount_rate,
        }
        return cls(
            profile=detail.profile,
            sales_summary=detail.sales_summary,
            trend_summary=detail.trend,
            top_colors=_normalize_rows(detail.color_summary.colors, top_n),
            top_sizes=_normalize_rows(detail.size_summary.sizes, top_n),
            top_regions=_normalize_rows(detail.region_summary.regions, top_n),
            top_stores=_normalize_rows(detail.store_summary.stores, top_n),
            discount_summary=discount_summary,
            latest_activity=list(getattr(detail.ai_context, "latest_activity", [])[:top_n]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": asdict(self.profile),
            "sales_summary": asdict(self.sales_summary),
            "trend_summary": asdict(self.trend_summary),
            "top_colors": self.top_colors,
            "top_sizes": self.top_sizes,
            "top_regions": self.top_regions,
            "top_stores": self.top_stores,
            "discount_summary": self.discount_summary,
            "latest_activity": self.latest_activity,
        }

    def to_prompt_text(self) -> str:
        lines: list[str] = []
        profile = self.to_dict()["profile"]
        sales = self.to_dict()["sales_summary"]
        trend = self.to_dict()["trend_summary"]

        lines.append("Product AI Context")
        lines.append("Profile")
        lines.append(f"- Product: {profile.get('product_name', '')}")
        lines.append(f"- Code: {profile.get('product_code', '')}")
        lines.append(f"- Year: {profile.get('year', '')}")
        lines.append(f"- Season: {profile.get('season_name', '')}")
        lines.append(f"- Wave: {profile.get('wave', '')}")
        lines.append(f"- Designer: {profile.get('designer_name', '')}")
        lines.append(f"- Category: {profile.get('category_name', '')} · {profile.get('big_category_name', '')}")
        lines.append("Sales Summary")
        lines.append(f"- Sales Qty: {_format_number(sales.get('sales_qty'), 0)}")
        lines.append(f"- Sales Amount: {_format_number(sales.get('sales_amount'))}")
        lines.append(f"- Avg Unit Price: {_format_number(sales.get('average_unit_price'))}")
        lines.append(f"- Avg Standard Price: {_format_number(sales.get('average_standard_price'))}")
        lines.append(f"- Discount Rate: {self.discount_summary.get('average_discount_rate', 0):.2%}")
        lines.append(f"- Transaction Count: {_format_number(sales.get('transaction_count'), 0)}")
        lines.append(f"- Store Count: {_format_number(sales.get('store_count'), 0)}")
        lines.append(f"- Color Count: {_format_number(sales.get('color_count'), 0)}")
        lines.append(f"- Size Count: {_format_number(sales.get('size_count'), 0)}")
        lines.append("Trend Summary")
        lines.append(f"- First Date: {trend.get('first_date', '')}")
        lines.append(f"- Last Date: {trend.get('last_date', '')}")
        lines.append(f"- Peak Amount: {_format_number(trend.get('peak_amount'))}")
        lines.append(f"- Trend Points: {_format_number(trend.get('total_points'), 0)}")
        lines.append("Top Colors")
        lines.extend([f"- {item.get('color_name', '')}: qty={_format_number(item.get('sales_qty'), 0)}, amount={_format_number(item.get('sales_amount'))}" for item in self.top_colors] or ["- None"])
        lines.append("Top Sizes")
        lines.extend([f"- {item.get('size_name', '')}: qty={_format_number(item.get('sales_qty'), 0)}, amount={_format_number(item.get('sales_amount'))}" for item in self.top_sizes] or ["- None"])
        lines.append("Top Regions")
        lines.extend([f"- {item.get('region_name', '')}: qty={_format_number(item.get('sales_qty'), 0)}, amount={_format_number(item.get('sales_amount'))}" for item in self.top_regions] or ["- None"])
        lines.append("Top Stores")
        lines.extend([f"- {item.get('store_name', '')}: qty={_format_number(item.get('sales_qty'), 0)}, amount={_format_number(item.get('sales_amount'))}" for item in self.top_stores] or ["- None"])
        lines.append("Latest Activity")
        lines.extend([
            f"- {item.get('sale_date', '')} | {item.get('document_no', '')} | {item.get('document_type', '')} | {item.get('store_code', '')} | {item.get('qty', '')} | {item.get('amount', '')}"
            for item in self.latest_activity
        ] or ["- None"])
        return "\n".join(lines)


def build_product_ai_context(detail: ProductDetail, top_n: int = 5) -> ProductAIContext:
    return ProductAIContext.from_product_detail(detail, top_n=top_n)