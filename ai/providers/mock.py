from __future__ import annotations

import re
from typing import Any

from ai.providers.base import AIProvider


def _extract_value(pattern: str, text: str) -> str:
    match = re.search(pattern, text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _extract_lines(section_name: str, text: str, limit: int = 3) -> list[str]:
    lines = text.splitlines()
    collected: list[str] = []
    in_section = False
    for line in lines:
        if line.strip() == section_name:
            in_section = True
            continue
        if in_section and line and not line.startswith("-") and not line.startswith(" "):
            break
        if in_section and line.startswith("-"):
            collected.append(line[2:].strip())
            if len(collected) >= limit:
                break
    return collected


class MockProvider(AIProvider):
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        latest_data_date = _extract_value(r"^- Latest Data Date:\s*(.+)$", user_prompt)
        total_sales_amount = _extract_value(r"^- Total Sales Amount:\s*(.+)$", user_prompt)
        total_sales_qty = _extract_value(r"^- Total Sales Qty:\s*(.+)$", user_prompt)
        average_discount_rate = _extract_value(r"^- Average Discount Rate:\s*(.+)$", user_prompt)
        top_products = _extract_lines("Top Products", user_prompt, limit=3)
        alerts = _extract_lines("Alerts Placeholder", user_prompt, limit=2)

        summary_lines = ["🤖 AI 今日经营简报", "", f"数据日期：{latest_data_date or '暂无'}", f"销售额：{total_sales_amount or '暂无'}", f"销售量：{total_sales_qty or '暂无'}", f"平均折扣率：{average_discount_rate or '暂无'}"]
        if top_products:
            summary_lines.append("重点商品：")
            summary_lines.extend([f"- {line}" for line in top_products])
        else:
            summary_lines.append("重点商品：暂无")
        if alerts:
            summary_lines.append("提醒：")
            summary_lines.extend([f"- {line}" for line in alerts])
        else:
            summary_lines.append("提醒：当前无可识别风险")
        return "\n".join(summary_lines)