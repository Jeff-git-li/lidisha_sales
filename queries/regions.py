from __future__ import annotations

from database import get_db_connection


REGION_GROUPS: dict[str, list[str]] = {
    "全国": [],
    "北区": ["华北", "东北", "西北"],
    "中区": ["华中", "西南", "华东", "河南"],
    "南区": ["华南"],
}


def expand_region_values(region_values: list[str] | None) -> list[str] | None:
    selected = [value for value in (region_values or []) if value and value != "全国"]
    if not selected:
        return None
    expanded: list[str] = []
    for value in selected:
        members = REGION_GROUPS.get(value)
        if members:
            expanded.extend(members)
        else:
            expanded.append(value)
    return list(dict.fromkeys(expanded))


def get_region_options() -> list[dict[str, str]]:
    excluded = set(REGION_GROUPS) | {member for members in REGION_GROUPS.values() for member in members} | {"未定义"}
    with get_db_connection() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT COALESCE(NULLIF(TRIM(region_name), ''), '') AS value
            FROM dim_store
            WHERE COALESCE(NULLIF(TRIM(region_name), ''), '') <> ''
            ORDER BY value
            """
        ).fetchall()
    values = [str(row["value"]) for row in rows if str(row["value"]) not in excluded]
    return [{"value": value, "label": value} for value in values]
