from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from queries.retail_queries import JOINED_CTE, _query_all, _query_one


def _latest_sale_date() -> str:
    row = _query_one("SELECT COALESCE(MAX(sale_date), '') AS latest_sale_date FROM fact_retail_sales")
    return str(row.get("latest_sale_date", "") or "")


def _store_base_cte() -> str:
    return """
    store_base AS (
        SELECT
            store_code,
            COALESCE(NULLIF(TRIM(store_name), ''), COALESCE(NULLIF(TRIM(store_code), ''), '未命名门店')) AS store_name,
            COALESCE(NULLIF(TRIM(region_name), ''), '未分区') AS region_name,
            COALESCE(NULLIF(TRIM(channel_code), ''), '') AS channel_code,
            COALESCE(NULLIF(TRIM(store_type_name), ''), '未分类') AS store_type_name
        FROM dim_store
        UNION
        SELECT DISTINCT
            f.store_code,
            COALESCE(NULLIF(TRIM(f.store_code), ''), '未命名门店') AS store_name,
            '未分区' AS region_name,
            '' AS channel_code,
            '未分类' AS store_type_name
        FROM fact_retail_sales f
        LEFT JOIN dim_store s ON s.store_code = f.store_code
        WHERE s.store_code IS NULL
          AND COALESCE(NULLIF(TRIM(f.store_code), ''), '') <> ''
    ),
    current_sales AS (
        SELECT
            store_code,
            COUNT(*) AS current_rows,
            COALESCE(SUM(qty), 0) AS current_sales_qty,
            COALESCE(SUM(effective_amount), 0) AS current_sales_amount,
            COALESCE(SUM(standard_amount), 0) AS current_standard_amount,
            COUNT(DISTINCT sale_date) AS current_active_days
        FROM joined
        WHERE sale_date BETWEEN ? AND ?
        GROUP BY store_code
    ),
    prior_sales AS (
        SELECT
            store_code,
            COUNT(*) AS prior_rows,
            COALESCE(SUM(qty), 0) AS prior_sales_qty,
            COALESCE(SUM(effective_amount), 0) AS prior_sales_amount,
            COALESCE(SUM(standard_amount), 0) AS prior_standard_amount,
            COUNT(DISTINCT sale_date) AS prior_active_days
        FROM joined
        WHERE sale_date BETWEEN ? AND ?
        GROUP BY store_code
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


def _store_rows_sql() -> tuple[str, list[Any]]:
    latest_sale_date = _latest_sale_date()
    if not latest_sale_date:
        return "", []
    end_date = date.fromisoformat(latest_sale_date)
    current_start = (end_date - timedelta(days=29)).isoformat()
    prior_end = (end_date - timedelta(days=30)).isoformat()
    prior_start = (end_date - timedelta(days=59)).isoformat()
    sql = f"""
    {_compose_cte(JOINED_CTE, _store_base_cte())}
    SELECT
        base.store_code,
        base.store_name,
        base.region_name,
        base.channel_code,
        base.store_type_name,
        COALESCE(current_sales.current_rows, 0) AS current_rows,
        COALESCE(current_sales.current_sales_qty, 0) AS current_sales_qty,
        COALESCE(current_sales.current_sales_amount, 0) AS current_sales_amount,
        COALESCE(current_sales.current_standard_amount, 0) AS current_standard_amount,
        COALESCE(current_sales.current_active_days, 0) AS current_active_days,
        CASE
            WHEN COALESCE(current_sales.current_standard_amount, 0) > 0
                THEN COALESCE(current_sales.current_sales_amount, 0) * 1.0 / current_sales.current_standard_amount
            ELSE NULL
        END AS current_discount_rate,
        COALESCE(prior_sales.prior_rows, 0) AS prior_rows,
        COALESCE(prior_sales.prior_sales_qty, 0) AS prior_sales_qty,
        COALESCE(prior_sales.prior_sales_amount, 0) AS prior_sales_amount,
        COALESCE(prior_sales.prior_standard_amount, 0) AS prior_standard_amount,
        COALESCE(prior_sales.prior_active_days, 0) AS prior_active_days,
        CASE
            WHEN COALESCE(prior_sales.prior_standard_amount, 0) > 0
                THEN COALESCE(prior_sales.prior_sales_amount, 0) * 1.0 / prior_sales.prior_standard_amount
            ELSE NULL
        END AS prior_discount_rate,
        COALESCE(current_sales.current_sales_amount, 0) - COALESCE(prior_sales.prior_sales_amount, 0) AS growth_amount,
        CASE
            WHEN COALESCE(prior_sales.prior_sales_amount, 0) > 0
                THEN (COALESCE(current_sales.current_sales_amount, 0) - prior_sales.prior_sales_amount) * 1.0 / prior_sales.prior_sales_amount
            ELSE NULL
        END AS growth_rate,
        CASE
            WHEN COALESCE(current_sales.current_rows, 0) > 0
                THEN COALESCE(current_sales.current_sales_amount, 0) * 1.0 / current_sales.current_rows
            ELSE NULL
        END AS average_ticket_amount
    FROM store_base base
    LEFT JOIN current_sales ON current_sales.store_code = base.store_code
    LEFT JOIN prior_sales ON prior_sales.store_code = base.store_code
    ORDER BY current_sales_amount DESC, current_sales_qty DESC, base.store_name ASC, base.store_code ASC
    """
    return sql, [current_start, latest_sale_date, prior_start, prior_end]


def load_store_analysis_raw(selected_store_code: str | None = None) -> dict[str, Any]:
    sql, params = _store_rows_sql()
    if not sql:
        return {
            "available": False,
            "period": {"latest_sale_date": "", "current_start_date": "", "current_end_date": "", "previous_start_date": "", "previous_end_date": "", "label": ""},
            "store_rows": [],
            "selected_store_code": (selected_store_code or "").strip(),
        }
    rows = _query_all(sql, params)
    latest_sale_date = _latest_sale_date()
    end_date = date.fromisoformat(latest_sale_date)
    current_start = (end_date - timedelta(days=29)).isoformat()
    prior_end = (end_date - timedelta(days=30)).isoformat()
    prior_start = (end_date - timedelta(days=59)).isoformat()
    return {
        "available": True,
        "period": {
            "latest_sale_date": latest_sale_date,
            "current_start_date": current_start,
            "current_end_date": latest_sale_date,
            "previous_start_date": prior_start,
            "previous_end_date": prior_end,
            "label": f"近30天门店销售：{current_start} 至 {latest_sale_date}",
            "comparison_label": f"对比前30天：{prior_start} 至 {prior_end}",
        },
        "store_rows": rows,
        "selected_store_code": (selected_store_code or "").strip(),
    }