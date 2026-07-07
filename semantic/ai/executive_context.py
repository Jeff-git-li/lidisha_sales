from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from database import get_db_connection
from queries.dashboard import get_dashboard_kpis
from queries.products import get_product_explorer
from queries.retail_queries import get_sales_summary


def _format_number(value: Any, digits: int = 2) -> str:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        number = 0.0
    if digits == 0:
        return f"{number:,.0f}"
    return f"{number:,.{digits}f}"


def _as_dict_rows(rows: list[Any], limit: int | None = None) -> list[dict[str, Any]]:
    selected = rows if limit is None else rows[:limit]
    result: list[dict[str, Any]] = []
    for row in selected:
        if hasattr(row, "__dataclass_fields__"):
            result.append(asdict(row))
        elif isinstance(row, dict):
            result.append(dict(row))
        else:
            result.append(dict(row))
    return result


@dataclass(slots=True)
class ExecutiveAIContext:
    latest_data_date: str
    total_sales_amount: float
    total_sales_qty: float
    average_discount_rate: float
    top_products: list[dict[str, Any]] = field(default_factory=list)
    weak_products: list[dict[str, Any]] = field(default_factory=list)
    region_summary: list[dict[str, Any]] = field(default_factory=list)
    alerts: list[dict[str, Any]] = field(default_factory=list)
    dashboard_summary: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_sources(cls, top_n: int = 10) -> "ExecutiveAIContext":
        dashboard_summary = get_dashboard_kpis(None)
        sales_summary = get_sales_summary(None)
        top_products, _ = get_product_explorer(page=1, per_page=top_n, sort="sales_amount", order="desc")
        latest_data_date = str(sales_summary.get("max_sale_date", "") or "")
        with get_db_connection() as conn:
            discount_row = conn.execute(
                "SELECT COALESCE(AVG(discount_rate), 0) AS average_discount_rate FROM fact_retail_sales"
            ).fetchone()
        average_discount_rate = float(discount_row[0] or 0) if discount_row else 0.0
        region_summary = [
            {"label": "待接入", "value": "region_summary_placeholder"}
        ]
        weak_products = [
            {"label": "待接入", "value": "weak_products_placeholder"}
        ]
        alerts = [
            {"label": "待接入", "value": "alerts_placeholder"}
        ]
        return cls(
            latest_data_date=latest_data_date,
            total_sales_amount=float(dashboard_summary.get("总销售额", 0) or 0),
            total_sales_qty=float(dashboard_summary.get("总销量", 0) or 0),
            average_discount_rate=average_discount_rate,
            top_products=_as_dict_rows(top_products, top_n),
            weak_products=weak_products,
            region_summary=region_summary,
            alerts=alerts,
            dashboard_summary={
                "总销售额": float(dashboard_summary.get("总销售额", 0) or 0),
                "总销量": float(dashboard_summary.get("总销量", 0) or 0),
                "核心款数": float(dashboard_summary.get("核心款数", 0) or 0),
                "商店数": float(dashboard_summary.get("商店数", 0) or 0),
                "日均销量": float(dashboard_summary.get("日均销量", 0) or 0),
                "latest_data_date": latest_data_date,
            },
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "latest_data_date": self.latest_data_date,
            "total_sales_amount": self.total_sales_amount,
            "total_sales_qty": self.total_sales_qty,
            "average_discount_rate": self.average_discount_rate,
            "top_products": self.top_products,
            "weak_products": self.weak_products,
            "region_summary": self.region_summary,
            "alerts": self.alerts,
            "dashboard_summary": self.dashboard_summary,
        }

    def to_prompt_text(self) -> str:
        lines = ["Executive AI Context"]
        lines.append("Core KPIs")
        lines.append(f"- Latest Data Date: {self.latest_data_date}")
        lines.append(f"- Total Sales Amount: {_format_number(self.total_sales_amount)}")
        lines.append(f"- Total Sales Qty: {_format_number(self.total_sales_qty, 0)}")
        lines.append(f"- Average Discount Rate: {self.average_discount_rate:.2%}")
        lines.append("Top Products")
        lines.extend([
            f"- {item.get('product_name', '')} ({item.get('product_code', '')}): amount={_format_number(item.get('sales_amount'))}, qty={_format_number(item.get('sales_qty', item.get('qty', 0)), 0)}"
            for item in self.top_products
        ] or ["- None"])
        lines.append("Weak Products Placeholder")
        lines.extend([f"- {item.get('label', '')}: {item.get('value', '')}" for item in self.weak_products] or ["- None"])
        lines.append("Region Summary Placeholder")
        lines.extend([f"- {item.get('label', '')}: {item.get('value', '')}" for item in self.region_summary] or ["- None"])
        lines.append("Alerts Placeholder")
        lines.extend([f"- {item.get('label', '')}: {item.get('value', '')}" for item in self.alerts] or ["- None"])
        return "\n".join(lines)


def build_executive_ai_context(top_n: int = 10) -> ExecutiveAIContext:
    return ExecutiveAIContext.from_sources(top_n=top_n)