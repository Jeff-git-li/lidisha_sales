from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


FILTER_COLUMN_MAP = {
    "region_name": "region_name",
    "channel_code": "channel_code",
    "store_name": "store_name",
    "store_code": "store_code",
    "store_type_name": "store_type_name",
    "source_file": "source_file",
    "category_name": "category_name",
    "big_category_name": "big_category_name",
    "year": "year",
    "season_name": "season_name",
    "wave": "wave",
    "designer_name": "designer_name",
    "product_code": "product_code",
}


def normalize_filter_values(filters: Mapping[str, Any] | None) -> dict[str, list[str]]:
    normalized: dict[str, list[str]] = {}
    if not filters:
        return normalized

    for key, value in filters.items():
        if value is None:
            continue
        if isinstance(value, (str, bytes)):
            values = [str(value).strip()]
        elif isinstance(value, Iterable):
            values = [str(item).strip() for item in value]
        else:
            values = [str(value).strip()]
        cleaned = [item for item in values if item]
        if cleaned:
            normalized[key] = list(dict.fromkeys(cleaned))
    return normalized


def build_date_filter(filters: Mapping[str, Any] | None) -> tuple[str, list[Any]]:
    normalized = normalize_filter_values(filters)
    clauses: list[str] = []
    params: list[Any] = []

    start_date = normalized.get("start_date", [])
    end_date = normalized.get("end_date", [])
    if start_date:
        clauses.append("sale_date >= ?")
        params.append(start_date[0])
    if end_date:
        clauses.append("sale_date <= ?")
        params.append(end_date[0])

    if not clauses:
        return "", []
    return " AND ".join(clauses), params


def build_core_product_filter(core_only: bool = True) -> str:
    if not core_only:
        return ""
    return "COALESCE(NULLIF(TRIM(year), ''), '') <> '' AND COALESCE(NULLIF(TRIM(season_name), ''), '') <> ''"


def build_dimension_joins() -> str:
    return """
        LEFT JOIN dim_product p ON f.product_code = p.product_code
        LEFT JOIN dim_store s ON f.store_code = s.store_code
        LEFT JOIN dim_calendar c ON f.date_key = c.date_key
    """


def build_parameters(filters: Mapping[str, Any] | None) -> list[Any]:
    _, params = build_where_clause(filters)
    return params


def build_where_clause(filters: Mapping[str, Any] | None, core_only: bool = True) -> tuple[str, list[Any]]:
    normalized = normalize_filter_values(filters)
    clauses: list[str] = []
    params: list[Any] = []

    date_clause, date_params = build_date_filter(normalized)
    if date_clause:
        clauses.append(date_clause)
        params.extend(date_params)

    for key, column in FILTER_COLUMN_MAP.items():
        values = normalized.get(key, [])
        if not values:
            continue
        placeholders = ", ".join(["?"] * len(values))
        clauses.append(f"COALESCE(NULLIF(TRIM({column}), ''), '') IN ({placeholders})")
        params.extend(values)

    core_clause = build_core_product_filter(core_only)
    if core_clause:
        clauses.append(core_clause)

    if not clauses:
        return "", params
    return " WHERE " + " AND ".join(clauses), params
