from __future__ import annotations

import hashlib
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from config import AUTO_REFRESH_HOUR, AUTO_REFRESH_MINUTE
from database import get_db_connection
from importers.sales_importer import DAILY_EXPORT_DIR, DAILY_IMPORT_LOCK_PATH, list_daily_sales_files
from queries.inventory import get_inventory_quantity_summary_bundle


def _is_missing_schema_error(exc: sqlite3.OperationalError) -> bool:
    message = str(exc).lower()
    return "no such table" in message or "no such column" in message or "has no column named" in message


def _query_one(conn: sqlite3.Connection, sql: str, params: list[Any] | tuple[Any, ...] | None = None, default: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        row = conn.execute(sql, params or []).fetchone()
    except sqlite3.OperationalError as exc:
        if _is_missing_schema_error(exc):
            return dict(default or {})
        raise
    if not row:
        return dict(default or {})
    return dict(row)


def _query_all(conn: sqlite3.Connection, sql: str, params: list[Any] | tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
    try:
        rows = conn.execute(sql, params or []).fetchall()
    except sqlite3.OperationalError as exc:
        if _is_missing_schema_error(exc):
            return []
        raise
    return [dict(row) for row in rows]


def _basename(path_value: str | None) -> str:
    if not path_value:
        return ""
    return Path(path_value).name


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _normalize_status(value: str | None) -> str:
    status = str(value or "").strip().lower()
    if status in {"success", "succeeded", "done"}:
        return "Success"
    if status in {"failed", "error", "fail"}:
        return "Failed"
    if status in {"skipped", "skipped_duplicate", "skipped_failed_unchanged"}:
        return "Skipped"
    if status in {"running", "processing"}:
        return "Running"
    return "Unknown"


def _safe_int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_queue_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    queue_files = list_daily_sales_files(DAILY_EXPORT_DIR)
    file_hashes = [_file_hash(path) for path in queue_files]
    registry_map: dict[str, dict[str, Any]] = {}
    if file_hashes:
        placeholders = ", ".join(["?"] * len(file_hashes))
        for row in _query_all(
            conn,
            f"""
            SELECT file_hash, status, imported_at, rows_read, rows_imported, rows_replaced, rows_rejected, error_message
            FROM daily_sales_import_registry
            WHERE file_hash IN ({placeholders})
            """,
            file_hashes,
        ):
            registry_map[str(row.get("file_hash", "") or "")] = row

    source_presence: dict[str, bool] = {}
    source_files = [str(path.resolve()) for path in queue_files]
    if source_files:
        placeholders = ", ".join(["?"] * len(source_files))
        for row in _query_all(
            conn,
            f"""
            SELECT source_file, COUNT(*) AS row_count
            FROM fact_retail_sales
            WHERE source_file IN ({placeholders})
            GROUP BY source_file
            """,
            source_files,
        ):
            source_presence[str(row.get("source_file", "") or "")] = _safe_int(row.get("row_count")) > 0

    queue_items: list[dict[str, Any]] = []
    pending_count = 0
    for path, file_hash in zip(queue_files, file_hashes):
        source_file = str(path.resolve())
        registry_row = registry_map.get(file_hash)
        imported_at = ""
        registry_status = "Unknown"
        pending = False
        next_action = "skipped"
        if registry_row:
            registry_status = _normalize_status(registry_row.get("status"))
            imported_at = str(registry_row.get("imported_at", "") or "")
            if registry_status in {"Success", "Failed"}:
                next_action = "skipped"
            else:
                pending = True
                next_action = "replaced" if source_presence.get(source_file, False) else "retried"
        else:
            pending = True
            next_action = "replaced" if source_presence.get(source_file, False) else "imported"

        if pending:
            pending_count += 1

        queue_items.append(
            {
                "filename": path.name,
                "sha256": file_hash,
                "registry_status": registry_status,
                "imported_at": imported_at,
                "pending": pending,
                "pending_label": "Yes" if pending else "No",
                "next_action": next_action,
                "next_action_label": next_action,
                "next_action_class": {
                    "imported": "primary",
                    "skipped": "secondary",
                    "retried": "warning",
                    "replaced": "info",
                }.get(next_action, "secondary"),
            }
        )

    skipped_or_processed_count = len(queue_files) - pending_count
    return {
        "directory": "exports/sales/daily",
        "folder_file_count": len(queue_files),
        "pending_file_count": pending_count,
        "skipped_or_processed_file_count": skipped_or_processed_count,
        "total_file_count": len(queue_files),
        "files": queue_items,
    }


def _load_lock_summary() -> dict[str, Any]:
    path = Path(DAILY_IMPORT_LOCK_PATH)
    if not path.exists():
        return {
            "exists": False,
            "age_seconds": None,
            "modified_at": "",
            "file_name": ".daily_import.lock",
            "state": "Free",
            "age_label": "Free",
        }
    try:
        stat_result = path.stat()
        modified_at = datetime.fromtimestamp(stat_result.st_mtime).isoformat(timespec="seconds")
        age_seconds = max(0.0, datetime.now().timestamp() - stat_result.st_mtime)
    except OSError:
        modified_at = ""
        age_seconds = None
    return {
        "exists": True,
        "age_seconds": age_seconds,
        "modified_at": modified_at,
        "file_name": ".daily_import.lock",
        "state": "Active" if age_seconds is not None and age_seconds <= 30 * 60 else "Possibly stale",
        "age_label": "--" if age_seconds is None else f"{int(age_seconds // 60)} min",
    }


def _load_scheduler_summary() -> dict[str, Any]:
    thread_running = any(thread.name == "daily-auto-refresh" and thread.is_alive() for thread in threading.enumerate())
    return {
        "running": thread_running,
        "thread_name": "daily-auto-refresh",
        "schedule_label": f"每天 {AUTO_REFRESH_HOUR:02d}:{AUTO_REFRESH_MINUTE:02d}",
    }


def _load_sales_section(conn: sqlite3.Connection, history_rows: list[dict[str, Any]], queue_summary: dict[str, Any]) -> dict[str, Any]:
    metrics = _query_one(
        conn,
        """
        SELECT
            COUNT(*) AS total_rows,
            COUNT(DISTINCT product_code) AS unique_products,
            COUNT(DISTINCT store_code) AS unique_stores,
            COALESCE(MIN(sale_date), '') AS earliest_sales_date,
            COALESCE(MAX(sale_date), '') AS latest_sales_date
        FROM fact_retail_sales
        """,
        default={
            "total_rows": 0,
            "unique_products": 0,
            "unique_stores": 0,
            "earliest_sales_date": "",
            "latest_sales_date": "",
        },
    )
    registry_stats = _query_one(
        conn,
        """
        SELECT
            SUM(CASE WHEN status = 'skipped_duplicate' THEN 1 ELSE 0 END) AS duplicate_skipped_file_count,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_daily_file_count
        FROM daily_sales_import_registry
        """,
        default={"duplicate_skipped_file_count": 0, "failed_daily_file_count": 0},
    )
    latest_success = next((row for row in history_rows if row.get("status") == "Success"), {})
    latest_failure = next((row for row in history_rows if row.get("status") == "Failed"), {})
    return {
        "available": True,
        "latest_sales_date": str(metrics.get("latest_sales_date", "") or ""),
        "earliest_sales_date": str(metrics.get("earliest_sales_date", "") or ""),
        "total_rows": _safe_int(metrics.get("total_rows")),
        "unique_products": _safe_int(metrics.get("unique_products")),
        "unique_stores": _safe_int(metrics.get("unique_stores")),
        "last_successful_import_time": str(latest_success.get("time", "") or ""),
        "last_successful_filename": str(latest_success.get("filename", "") or ""),
        "last_failed_import_time": str(latest_failure.get("time", "") or ""),
        "last_failed_filename": str(latest_failure.get("filename", "") or ""),
        "last_imported_filename": str(latest_success.get("filename", "") or ""),
        "last_imported_row_count": _safe_int(latest_success.get("rows_imported")),
        "queue_file_count": _safe_int(queue_summary.get("pending_file_count")),
        "queue_folder_file_count": _safe_int(queue_summary.get("folder_file_count")),
        "queue_pending_file_count": _safe_int(queue_summary.get("pending_file_count")),
        "queue_skipped_or_processed_file_count": _safe_int(queue_summary.get("skipped_or_processed_file_count")),
        "duplicate_skipped_file_count": _safe_int(registry_stats.get("duplicate_skipped_file_count")),
        "failed_daily_file_count": _safe_int(registry_stats.get("failed_daily_file_count")),
    }


def _load_inventory_section(conn: sqlite3.Connection) -> dict[str, Any]:
    latest_row = _query_one(
        conn,
        """
        SELECT inventory_date, imported_at, source_file
        FROM fact_inventory_snapshot
        ORDER BY inventory_date DESC, imported_at DESC
        LIMIT 1
        """,
        default={"inventory_date": "", "imported_at": "", "source_file": ""},
    )
    latest_inventory_date = str(latest_row.get("inventory_date", "") or "")
    inventory_bundle = get_inventory_quantity_summary_bundle(latest_inventory_date) if latest_inventory_date else {}
    return {
        "available": True,
        "latest_inventory_date": latest_inventory_date,
        "total_rows": _safe_int(inventory_bundle.get("total_rows")),
        "total_inventory_quantity": _safe_float(inventory_bundle.get("all_inventory_qty")),
        "unique_products": _safe_int(inventory_bundle.get("unique_products")),
        "unique_warehouses": _safe_int(inventory_bundle.get("unique_warehouses")),
        "terminal_inventory_quantity": _safe_float(inventory_bundle.get("terminal_inventory_qty")),
        "all_inventory_quantity": _safe_float(inventory_bundle.get("all_inventory_qty")),
        "terminal_warehouse_count": _safe_int(inventory_bundle.get("terminal_warehouse_count")),
        "all_warehouse_count": _safe_int(inventory_bundle.get("all_warehouse_count")),
        "last_inventory_import_time": str(latest_row.get("imported_at", "") or ""),
        "current_source_filename": _basename(str(latest_row.get("source_file", "") or "")),
    }


def _load_master_section(conn: sqlite3.Connection) -> dict[str, Any]:
    metrics = _query_one(
        conn,
        """
        WITH
        sales_unknown_product AS (
            SELECT COUNT(DISTINCT f.product_code) AS value
            FROM fact_retail_sales f
            LEFT JOIN dim_product p ON p.product_code = f.product_code
            WHERE p.product_code IS NULL AND COALESCE(NULLIF(TRIM(f.product_code), ''), '') <> ''
        ),
        sales_unknown_store AS (
            SELECT COUNT(DISTINCT f.store_code) AS value
            FROM fact_retail_sales f
            LEFT JOIN dim_store s ON s.store_code = f.store_code
            WHERE s.store_code IS NULL AND COALESCE(NULLIF(TRIM(f.store_code), ''), '') <> ''
        ),
        inventory_unmapped_warehouse AS (
            SELECT COUNT(DISTINCT w.warehouse_code) AS value
            FROM dim_warehouse w
            LEFT JOIN dim_store s ON s.store_code = w.mapped_store_code
            WHERE COALESCE(NULLIF(TRIM(w.mapped_store_code), ''), '') = '' OR s.store_code IS NULL
        )
        SELECT
            (SELECT COUNT(*) FROM dim_product) AS product_count,
            (SELECT COUNT(*) FROM dim_store) AS store_count,
            (SELECT COUNT(*) FROM dim_warehouse) AS warehouse_count,
            (SELECT COUNT(*) FROM dim_channel) AS channel_count,
            (SELECT COUNT(*) FROM dim_product WHERE COALESCE(NULLIF(TRIM(category_name), ''), '') = '') AS products_missing_category,
            (SELECT COUNT(*) FROM dim_store WHERE COALESCE(NULLIF(TRIM(channel_code), ''), '') = '') AS stores_missing_channel,
            (SELECT value FROM inventory_unmapped_warehouse) AS inventory_warehouse_codes_not_mapped_to_dim_store,
            (SELECT value FROM sales_unknown_product) AS sales_product_codes_not_mapped_to_dim_product,
            (SELECT value FROM sales_unknown_store) AS sales_store_codes_not_mapped_to_dim_store
        """,
        default={
            "product_count": 0,
            "store_count": 0,
            "warehouse_count": 0,
            "channel_count": 0,
            "products_missing_category": 0,
            "stores_missing_channel": 0,
            "inventory_warehouse_codes_not_mapped_to_dim_store": 0,
            "sales_product_codes_not_mapped_to_dim_product": 0,
            "sales_store_codes_not_mapped_to_dim_store": 0,
        },
    )
    return {
        "available": True,
        "product_count": _safe_int(metrics.get("product_count")),
        "store_count": _safe_int(metrics.get("store_count")),
        "warehouse_count": _safe_int(metrics.get("warehouse_count")),
        "channel_count": _safe_int(metrics.get("channel_count")),
        "products_missing_category": _safe_int(metrics.get("products_missing_category")),
        "stores_missing_channel": _safe_int(metrics.get("stores_missing_channel")),
        "inventory_warehouse_codes_not_mapped_to_dim_store": _safe_int(metrics.get("inventory_warehouse_codes_not_mapped_to_dim_store")),
        "sales_product_codes_not_mapped_to_dim_product": _safe_int(metrics.get("sales_product_codes_not_mapped_to_dim_product")),
        "sales_store_codes_not_mapped_to_dim_store": _safe_int(metrics.get("sales_store_codes_not_mapped_to_dim_store")),
    }


def _load_history_rows(conn: sqlite3.Connection, limit: int = 100) -> list[dict[str, Any]]:
    registry_rows = _query_all(
        conn,
        """
        SELECT
            file_hash,
            source_file,
            file_name,
            imported_at,
            status,
            rows_read,
            rows_imported,
            rows_replaced,
            duplicate_rows,
            rows_rejected,
            error_message,
            sales_date_min,
            sales_date_max
        FROM daily_sales_import_registry
        ORDER BY imported_at DESC, file_name ASC
        LIMIT ?
        """,
        [int(limit)],
    )
    log_rows = _query_all(
        conn,
        """
        SELECT
            load_batch_id,
            import_type,
            source_file,
            started_at,
            finished_at,
            rows_read,
            rows_imported,
            duplicate_rows,
            elapsed_seconds,
            status,
            message,
            unknown_product_rows,
            unknown_store_rows
        FROM import_log
        WHERE import_type = 'sales'
        ORDER BY finished_at DESC, source_file ASC
        LIMIT ?
        """,
        [int(limit)],
    )
    registry_sources = {str(row.get("source_file", "") or "") for row in registry_rows}
    log_by_source: dict[str, dict[str, Any]] = {str(row.get("source_file", "") or ""): row for row in log_rows if row.get("source_file")}
    history_rows: list[dict[str, Any]] = []

    for row in registry_rows:
        source_file = str(row.get("source_file", "") or "")
        log_row = log_by_source.get(source_file)
        status = _normalize_status(row.get("status"))
        message = str(row.get("error_message", "") or "")
        if not message:
            if status == "Success":
                message = "文件已成功导入"
            elif status == "Skipped":
                message = "文件已跳过"
        history_rows.append({
            "time": str(row.get("imported_at", "") or ""),
            "import_type": "sales",
            "filename": str(row.get("file_name", "") or _basename(source_file)),
            "status": status,
            "rows_read": _safe_int(row.get("rows_read")),
            "rows_imported": _safe_int(row.get("rows_imported")),
            "rows_rejected": _safe_int(row.get("rows_rejected")),
            "duplicates": _safe_int(row.get("duplicate_rows")),
            "duration_seconds": _safe_float(log_row.get("elapsed_seconds")) if log_row else None,
            "message": message,
            "source_kind": "daily_sales_import_registry",
            "source_file": source_file,
        })

    for row in log_rows:
        source_file = str(row.get("source_file", "") or "")
        if source_file in registry_sources:
            continue
        status = _normalize_status(row.get("status"))
        message = str(row.get("message", "") or "")
        if not message:
            message = "文件已成功导入" if status == "Success" else ""
        rows_read = _safe_int(row.get("rows_read"))
        rows_imported = _safe_int(row.get("rows_imported"))
        duplicate_rows = _safe_int(row.get("duplicate_rows"))
        rows_rejected = max(rows_read - rows_imported - duplicate_rows, 0)
        history_rows.append({
            "time": str(row.get("finished_at", "") or ""),
            "import_type": str(row.get("import_type", "") or "sales"),
            "filename": _basename(source_file),
            "status": status,
            "rows_read": rows_read,
            "rows_imported": rows_imported,
            "rows_rejected": rows_rejected,
            "duplicates": duplicate_rows,
            "duration_seconds": _safe_float(row.get("elapsed_seconds")),
            "message": message,
            "source_kind": "import_log",
            "source_file": source_file,
        })

    history_rows.sort(key=lambda item: item.get("time", ""), reverse=True)
    return history_rows[: int(limit)]


def _load_snapshot_section(conn: sqlite3.Connection, latest_sales_date: str, latest_successful_refresh_time: str) -> dict[str, Any]:
    snapshot_count_row = _query_one(
        conn,
        "SELECT COUNT(*) AS snapshot_row_count, COALESCE(MIN(snapshot_date), '') AS min_snapshot_date, COALESCE(MAX(snapshot_date), '') AS max_snapshot_date FROM dashboard_snapshot",
        default={"snapshot_row_count": 0, "min_snapshot_date": "", "max_snapshot_date": ""},
    )
    latest_row = _query_one(
        conn,
        """
        SELECT snapshot_date, latest_data_date, summary_text, action_text, total_qty, total_amount
        FROM dashboard_snapshot
        ORDER BY snapshot_date DESC
        LIMIT 1
        """,
        default={
            "snapshot_date": "",
            "latest_data_date": "",
            "summary_text": "",
            "action_text": "",
            "total_qty": 0,
            "total_amount": 0,
        },
    )
    latest_snapshot_date = str(latest_row.get("snapshot_date", "") or "")
    latest_data_date = str(latest_row.get("latest_data_date", "") or "")
    behind_latest_sales_date = bool(latest_sales_date and latest_data_date and latest_data_date < latest_sales_date)
    rebuild_required = not latest_snapshot_date or behind_latest_sales_date
    coverage_start = str(snapshot_count_row.get("min_snapshot_date", "") or "")
    coverage_end = str(snapshot_count_row.get("max_snapshot_date", "") or "")
    coverage_label = "Unknown"
    if coverage_start and coverage_end:
        coverage_label = f"{coverage_start} to {coverage_end}"
    elif latest_snapshot_date:
        coverage_label = latest_snapshot_date
    last_snapshot_result = " · ".join(part for part in [str(latest_row.get("summary_text", "") or ""), str(latest_row.get("action_text", "") or "")] if part)
    if not last_snapshot_result:
        last_snapshot_result = "No snapshot summary available"
    return {
        "available": True,
        "latest_snapshot_date": latest_snapshot_date,
        "latest_snapshot_build_time": str(latest_successful_refresh_time or ""),
        "snapshot_row_count": _safe_int(snapshot_count_row.get("snapshot_row_count")),
        "snapshot_date_coverage": coverage_label,
        "last_snapshot_result": last_snapshot_result,
        "behind_latest_sales_date": behind_latest_sales_date,
        "rebuild_required": rebuild_required,
        "latest_data_date": latest_data_date,
        "snapshot_total_qty": _safe_int(latest_row.get("total_qty")),
        "snapshot_total_amount": _safe_float(latest_row.get("total_amount")),
    }


def load_data_center_raw() -> dict[str, Any]:
    with get_db_connection() as conn:
        timings: dict[str, float] = {}
        section_started = time.perf_counter()
        queue_summary = _load_queue_summary(conn)
        lock_summary = _load_lock_summary()
        timings["filesystem/lock"] = (time.perf_counter() - section_started) * 1000

        section_started = time.perf_counter()
        scheduler_summary = _load_scheduler_summary()
        timings["scheduler"] = (time.perf_counter() - section_started) * 1000

        section_started = time.perf_counter()
        history_rows = _load_history_rows(conn, limit=100)
        timings["import history"] = (time.perf_counter() - section_started) * 1000

        section_started = time.perf_counter()
        sales = _load_sales_section(conn, history_rows, queue_summary)
        timings["sales"] = (time.perf_counter() - section_started) * 1000

        section_started = time.perf_counter()
        inventory = _load_inventory_section(conn)
        timings["inventory"] = (time.perf_counter() - section_started) * 1000

        section_started = time.perf_counter()
        master = _load_master_section(conn)
        timings["master-data quality"] = (time.perf_counter() - section_started) * 1000

        latest_successful_refresh_time = next((row.get("time", "") for row in history_rows if row.get("status") == "Success"), "")
        section_started = time.perf_counter()
        snapshot = _load_snapshot_section(conn, sales.get("latest_sales_date", ""), latest_successful_refresh_time)
        timings["snapshot"] = (time.perf_counter() - section_started) * 1000
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "queue": queue_summary,
        "lock": lock_summary,
        "scheduler": scheduler_summary,
        "sales": sales,
        "inventory": inventory,
        "master": master,
        "snapshot": snapshot,
        "history": history_rows[:20],
        "latest_successful_refresh_time": latest_successful_refresh_time,
        "timings": timings,
    }
