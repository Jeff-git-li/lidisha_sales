from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from database import get_db_connection
from importers.master_data_importer import _existing_columns, _float, _text, ensure_import_log_table
from logging_config import get_logger


logger = get_logger(__name__)

INVENTORY_REQUIRED_COLUMNS = ["商品代码", "仓库代码", "颜色名称", "尺码名称", "数量"]
INVENTORY_DATE_PATTERN = "日期:"
INVENTORY_TABLE = "fact_inventory_snapshot"


@dataclass(frozen=True)
class InventoryImportResult:
    source_file: str
    inventory_date: str
    rows_read: int
    rows_imported: int
    unique_products: int
    unique_warehouses: int
    positive_inventory_rows: int
    negative_inventory_rows: int
    net_inventory_quantity: float
    available_inventory_quantity: float
    unmatched_warehouse_count: int


def _find_header_row(ws) -> int:
    required = set(INVENTORY_REQUIRED_COLUMNS)
    for row_index, row in enumerate(ws.iter_rows(values_only=True), start=1):
        values = [_text(value) for value in row]
        if not any(values):
            continue
        if required.issubset({value for value in values if value}):
            return row_index
    raise ValueError("Unable to locate inventory header row")


def _extract_inventory_date(ws) -> str:
    for row_index in range(1, 9):
        for cell in ws[row_index]:
            value = _text(cell.value)
            if not value:
                continue
            if value.startswith(INVENTORY_DATE_PATTERN):
                inventory_date = value.split(INVENTORY_DATE_PATTERN, 1)[1].strip()
                if inventory_date:
                    return inventory_date
    raise ValueError("Inventory date is missing")


def _ensure_inventory_table(conn) -> None:
    desired_columns = [
        "inventory_date",
        "product_code",
        "warehouse_code",
        "color_name",
        "size_name",
        "raw_inventory_qty",
        "available_inventory_qty",
        "source_file",
        "imported_at",
    ]
    existing = _existing_columns(conn, INVENTORY_TABLE)
    if existing and existing != desired_columns:
        conn.execute(f"DROP TABLE IF EXISTS {INVENTORY_TABLE}")
        existing = []
    if not existing:
        conn.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS {INVENTORY_TABLE} (
                inventory_date TEXT NOT NULL,
                product_code TEXT NOT NULL,
                warehouse_code TEXT NOT NULL,
                color_name TEXT NOT NULL DEFAULT '',
                size_name TEXT NOT NULL DEFAULT '',
                raw_inventory_qty REAL NOT NULL DEFAULT 0,
                available_inventory_qty REAL NOT NULL DEFAULT 0,
                source_file TEXT NOT NULL,
                imported_at TEXT NOT NULL,
                UNIQUE (inventory_date, product_code, warehouse_code, color_name, size_name)
            );
            CREATE INDEX IF NOT EXISTS idx_fact_inventory_snapshot_date ON {INVENTORY_TABLE}(inventory_date);
            CREATE INDEX IF NOT EXISTS idx_fact_inventory_snapshot_product ON {INVENTORY_TABLE}(product_code);
            CREATE INDEX IF NOT EXISTS idx_fact_inventory_snapshot_warehouse ON {INVENTORY_TABLE}(warehouse_code);
            """
        )


def _flush_rows(conn, rows: list[tuple[Any, ...]]) -> int:
    if not rows:
        return 0
    before = conn.total_changes
    conn.executemany(
        f"""
        INSERT INTO {INVENTORY_TABLE} (
            inventory_date, product_code, warehouse_code, color_name, size_name,
            raw_inventory_qty, available_inventory_qty, source_file, imported_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(inventory_date, product_code, warehouse_code, color_name, size_name) DO UPDATE SET
            raw_inventory_qty=excluded.raw_inventory_qty,
            available_inventory_qty=excluded.available_inventory_qty,
            source_file=excluded.source_file,
            imported_at=excluded.imported_at
        """,
        rows,
    )
    return conn.total_changes - before


def import_inventory_file(path: str | Path, batch_size: int = 10000) -> dict[str, Any]:
    source_file = str(Path(path).resolve())
    workbook = load_workbook(path, read_only=True, data_only=True)
    ws = workbook[workbook.sheetnames[0]]
    header_row = _find_header_row(ws)
    headers = [_text(cell.value) for cell in ws[header_row]]
    required_set = set(INVENTORY_REQUIRED_COLUMNS)
    if not required_set.issubset({value for value in headers if value}):
        missing = sorted(required_set - {value for value in headers if value})
        raise ValueError(f"Inventory workbook is missing required columns: {', '.join(missing)}")

    inventory_date = _extract_inventory_date(ws)
    imported_at = datetime.now().isoformat(timespec="seconds")

    with get_db_connection() as conn:
        ensure_import_log_table(conn)
        _ensure_inventory_table(conn)

        warehouse_codes = {str(row[0]) for row in conn.execute("SELECT warehouse_code FROM dim_warehouse").fetchall()}
        if not warehouse_codes:
            raise ValueError("dim_warehouse is empty; import warehouses before inventory")

        rows_read = 0
        rows_imported = 0
        positive_inventory_rows = 0
        negative_inventory_rows = 0
        unmatched_warehouse_count = 0
        net_inventory_quantity = 0.0
        available_inventory_quantity = 0.0
        unique_products: set[str] = set()
        unique_warehouses: set[str] = set()
        unmatched_warehouses: set[str] = set()
        batch_rows: list[tuple[Any, ...]] = []

        for values in ws.iter_rows(min_row=header_row + 1, values_only=True):
            values = [_text(value) for value in values]
            if not any(values):
                continue
            record = {headers[i]: values[i] if i < len(values) else "" for i in range(len(headers))}
            product_code = _text(record.get("商品代码"))
            warehouse_code = _text(record.get("仓库代码"))
            color_name = _text(record.get("颜色名称"))
            size_name = _text(record.get("尺码名称"))
            raw_qty = _float(record.get("数量")) or 0.0

            rows_read += 1
            if raw_qty > 0:
                positive_inventory_rows += 1
            elif raw_qty < 0:
                negative_inventory_rows += 1
            net_inventory_quantity += raw_qty
            available_inventory_quantity += max(raw_qty, 0.0)
            if product_code:
                unique_products.add(product_code)
            if warehouse_code:
                unique_warehouses.add(warehouse_code)
            if warehouse_code not in warehouse_codes:
                unmatched_warehouses.add(warehouse_code)

            batch_rows.append((
                inventory_date,
                product_code,
                warehouse_code,
                color_name,
                size_name,
                raw_qty,
                max(raw_qty, 0.0),
                source_file,
                imported_at,
            ))

            if len(batch_rows) >= batch_size:
                rows_imported += _flush_rows(conn, batch_rows)
                batch_rows.clear()

        if batch_rows:
            rows_imported += _flush_rows(conn, batch_rows)

        if rows_read == 0:
            raise ValueError("Inventory workbook contains no data rows")
        if unmatched_warehouses:
            raise ValueError(f"Inventory workbook contains unknown warehouse codes: {', '.join(sorted(unmatched_warehouses))}")

        result = {
            "source_file": source_file,
            "inventory_date": inventory_date,
            "rows_read": rows_read,
            "rows_imported": rows_imported,
            "unique_products": len(unique_products),
            "unique_warehouses": len(unique_warehouses),
            "positive_inventory_rows": positive_inventory_rows,
            "negative_inventory_rows": negative_inventory_rows,
            "net_inventory_quantity": net_inventory_quantity,
            "available_inventory_quantity": available_inventory_quantity,
            "unmatched_warehouse_count": len(unmatched_warehouses),
        }
        conn.commit()
        return result
