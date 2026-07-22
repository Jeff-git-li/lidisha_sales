from __future__ import annotations

import hashlib
import json
import os
import stat as stat_module
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from database import get_db_connection
from importers.master_data_importer import ensure_import_log_table, ensure_sales_table, import_sales_file, rebuild_sales_table, write_import_log
from logging_config import get_logger


logger = get_logger(__name__)

DAILY_EXPORT_DIR = Path(__file__).resolve().parent.parent / "exports" / "daily"
DAILY_IMPORT_LOCK_PATH = DAILY_EXPORT_DIR / ".daily_import.lock"
DAILY_IMPORT_REGISTRY_TABLE = "daily_sales_import_registry"
SUPPORTED_DAILY_EXTENSIONS = {".xlsx", ".xls"}


def ensure_daily_import_registry_table(conn) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {DAILY_IMPORT_REGISTRY_TABLE} (
            file_hash TEXT PRIMARY KEY,
            source_file TEXT NOT NULL,
            file_name TEXT NOT NULL,
            file_size INTEGER NOT NULL DEFAULT 0,
            file_mtime REAL NOT NULL DEFAULT 0,
            imported_at TEXT NOT NULL,
            status TEXT NOT NULL,
            rows_read INTEGER NOT NULL DEFAULT 0,
            rows_imported INTEGER NOT NULL DEFAULT 0,
            rows_replaced INTEGER NOT NULL DEFAULT 0,
            duplicate_rows INTEGER NOT NULL DEFAULT 0,
            rows_rejected INTEGER NOT NULL DEFAULT 0,
            rejection_reasons TEXT,
            sales_date_min TEXT,
            sales_date_max TEXT,
            error_message TEXT
        )
        """
    )
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{DAILY_IMPORT_REGISTRY_TABLE}_source_file ON {DAILY_IMPORT_REGISTRY_TABLE}(source_file)"
    )
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{DAILY_IMPORT_REGISTRY_TABLE}_status ON {DAILY_IMPORT_REGISTRY_TABLE}(status)"
    )


def _failure_result(path: str | Path, started_at: str, exc: Exception) -> dict[str, int | float | str | dict[str, int]]:
    return {
        "source_file": str(Path(path).resolve()),
        "rows_read": 0,
        "rows_imported": 0,
        "duplicate_rows": 0,
        "unknown_product_rows": 0,
        "unknown_product_codes": "",
        "unknown_store_rows": 0,
        "unknown_store_codes": "",
        "unknown_products": 0,
        "unknown_stores": 0,
        "rows_rejected": 0,
        "rejection_reasons": {},
        "rows_replaced": 0,
        "sales_date_min": "",
        "sales_date_max": "",
        "load_batch_id": "",
        "import_run_time": started_at,
        "error_message": str(exc),
    }


def _build_import_log_entry(
    result: dict[str, int | float | str | dict[str, int]],
    *,
    started_at: str,
    finished_at: str,
    status: str,
    message: str,
) -> dict[str, object]:
    return {
        "load_batch_id": result.get("load_batch_id", ""),
        "import_type": "sales",
        "source_file": result.get("source_file", ""),
        "started_at": started_at,
        "finished_at": finished_at,
        "rows_read": int(result.get("rows_read", 0) or 0),
        "rows_imported": int(result.get("rows_imported", 0) or 0),
        "duplicate_rows": int(result.get("duplicate_rows", 0) or 0),
        "unknown_product_rows": int(result.get("unknown_product_rows", 0) or 0),
        "unknown_product_codes": str(result.get("unknown_product_codes", "") or ""),
        "unknown_store_rows": int(result.get("unknown_store_rows", 0) or 0),
        "unknown_store_codes": str(result.get("unknown_store_codes", "") or ""),
        "elapsed_seconds": round((datetime.fromisoformat(finished_at) - datetime.fromisoformat(started_at)).total_seconds(), 2),
        "status": status,
        "message": message,
    }


def import_sales_to_connection(
    conn,
    path: str | Path,
    *,
    batch_size: int = 10000,
    rebuild: bool = True,
    commit_batches: bool = True,
) -> dict[str, int | float | str | dict[str, int]]:
    if rebuild:
        rebuild_sales_table(conn)
    else:
        ensure_sales_table(conn)
    ensure_import_log_table(conn)
    return import_sales_file(
        conn,
        path,
        batch_size=batch_size,
        commit_batches=commit_batches,
        replace_source_file=not rebuild,
    )


def _json_text(value: dict[str, int] | None) -> str:
    return json.dumps(value or {}, ensure_ascii=False, sort_keys=True)


def write_daily_import_registry_entry(
    conn,
    *,
    file_hash: str,
    path: Path,
    status: str,
    result: dict[str, int | float | str | dict[str, int]],
    error_message: str = "",
) -> None:
    stat_result = path.stat()
    imported_at = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        f"""
        INSERT INTO {DAILY_IMPORT_REGISTRY_TABLE} (
            file_hash, source_file, file_name, file_size, file_mtime, imported_at, status,
            rows_read, rows_imported, rows_replaced, duplicate_rows, rows_rejected,
            rejection_reasons, sales_date_min, sales_date_max, error_message
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(file_hash) DO UPDATE SET
            source_file=excluded.source_file,
            file_name=excluded.file_name,
            file_size=excluded.file_size,
            file_mtime=excluded.file_mtime,
            imported_at=excluded.imported_at,
            status=excluded.status,
            rows_read=excluded.rows_read,
            rows_imported=excluded.rows_imported,
            rows_replaced=excluded.rows_replaced,
            duplicate_rows=excluded.duplicate_rows,
            rows_rejected=excluded.rows_rejected,
            rejection_reasons=excluded.rejection_reasons,
            sales_date_min=excluded.sales_date_min,
            sales_date_max=excluded.sales_date_max,
            error_message=excluded.error_message
        """,
        (
            file_hash,
            str(path.resolve()),
            path.name,
            int(stat_result.st_size),
            float(stat_result.st_mtime),
            imported_at,
            status,
            int(result.get("rows_read", 0) or 0),
            int(result.get("rows_imported", 0) or 0),
            int(result.get("rows_replaced", 0) or 0),
            int(result.get("duplicate_rows", 0) or 0),
            int(result.get("rows_rejected", 0) or 0),
            _json_text(result.get("rejection_reasons") if isinstance(result.get("rejection_reasons"), dict) else {}),
            str(result.get("sales_date_min", "") or ""),
            str(result.get("sales_date_max", "") or ""),
            error_message,
        ),
    )


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_hidden_file(path: Path) -> bool:
    if path.name.startswith("."):
        return True
    try:
        attributes = getattr(path.stat(), "st_file_attributes", 0)
    except OSError:
        return False
    hidden_mask = getattr(stat_module, "FILE_ATTRIBUTE_HIDDEN", 0)
    system_mask = getattr(stat_module, "FILE_ATTRIBUTE_SYSTEM", 0)
    return bool(attributes & (hidden_mask | system_mask))


def _is_ignored_daily_file(path: Path) -> bool:
    name = path.name
    lower_name = name.lower()
    if name.startswith("~$"):
        return True
    if _is_hidden_file(path):
        return True
    if path.suffix.lower() not in SUPPORTED_DAILY_EXTENSIONS:
        return True
    stem_parts = {part for part in path.stem.lower().split(".") if part}
    if {"failed", "archived", "processed"} & stem_parts:
        return True
    return False


def list_daily_sales_files(directory: str | Path = DAILY_EXPORT_DIR) -> list[Path]:
    daily_dir = Path(directory)
    if not daily_dir.exists():
        return []
    files = [path for path in daily_dir.iterdir() if path.is_file() and not _is_ignored_daily_file(path)]
    return sorted(files, key=lambda path: (path.stat().st_mtime, path.name.lower(), path.name))


@contextmanager
def daily_import_lock(lock_path: str | Path = DAILY_IMPORT_LOCK_PATH):
    path = Path(lock_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise RuntimeError(f"Daily sales import already running: {path}")
    try:
        payload = f"pid={os.getpid()} started_at={datetime.now().isoformat(timespec='seconds')}"
        os.write(descriptor, payload.encode("utf-8"))
        yield path
    finally:
        os.close(descriptor)
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def process_daily_sales_folder(directory: str | Path = DAILY_EXPORT_DIR, batch_size: int = 10000) -> dict[str, Any]:
    started = time.perf_counter()
    daily_dir = Path(directory)
    daily_dir.mkdir(parents=True, exist_ok=True)

    with get_db_connection() as conn:
        ensure_sales_table(conn)
        ensure_import_log_table(conn)
        ensure_daily_import_registry_table(conn)
        conn.commit()

    files = list_daily_sales_files(daily_dir)
    summary: dict[str, Any] = {
        "directory": str(daily_dir.resolve()),
        "scanned": len(files),
        "skipped": 0,
        "imported": 0,
        "failed": 0,
        "rows_imported": 0,
        "rows_replaced": 0,
        "rows_rejected": 0,
        "date_min": "",
        "date_max": "",
        "duration_seconds": 0.0,
        "files": [],
        "lock_skipped": False,
    }

    try:
        with daily_import_lock():
            logger.info("Daily sales scan started: %s", daily_dir)
            for path in files:
                logger.info("Daily sales file detected: %s", path.name)
                stat_result = path.stat()
                file_hash = _file_hash(path)
                file_record: dict[str, Any] = {
                    "file_name": path.name,
                    "source_file": str(path.resolve()),
                    "file_hash": file_hash,
                    "file_size": int(stat_result.st_size),
                    "file_mtime": float(stat_result.st_mtime),
                    "status": "pending",
                }
                with get_db_connection() as conn:
                    ensure_sales_table(conn)
                    ensure_import_log_table(conn)
                    ensure_daily_import_registry_table(conn)
                    existing = conn.execute(
                        f"SELECT status FROM {DAILY_IMPORT_REGISTRY_TABLE} WHERE file_hash = ?",
                        (file_hash,),
                    ).fetchone()
                    if existing and str(existing["status"] or "") == "success":
                        file_record["status"] = "skipped_duplicate"
                        summary["skipped"] += 1
                        summary["files"].append(file_record)
                        logger.info("Daily sales duplicate skipped: %s", path.name)
                        continue
                    if existing and str(existing["status"] or "") == "failed":
                        file_record["status"] = "skipped_failed_unchanged"
                        summary["skipped"] += 1
                        summary["files"].append(file_record)
                        logger.info("Daily sales failed-unchanged skipped: %s", path.name)
                        continue

                    started_at = datetime.now().isoformat(timespec="seconds")
                    try:
                        result = import_sales_to_connection(
                            conn,
                            path,
                            batch_size=batch_size,
                            rebuild=False,
                            commit_batches=False,
                        )
                    except Exception as exc:
                        conn.rollback()
                        failed_result = _failure_result(path, started_at, exc)
                        finished_at = datetime.now().isoformat(timespec="seconds")
                        write_import_log(
                            conn,
                            _build_import_log_entry(
                                failed_result,
                                started_at=started_at,
                                finished_at=finished_at,
                                status="failed",
                                message=str(exc),
                            ),
                        )
                        write_daily_import_registry_entry(
                            conn,
                            file_hash=file_hash,
                            path=path,
                            status="failed",
                            result=failed_result,
                            error_message=str(exc),
                        )
                        conn.commit()
                        file_record["status"] = "failed"
                        file_record["error_message"] = str(exc)
                        summary["failed"] += 1
                        summary["files"].append(file_record)
                        logger.exception("Daily sales import failed: %s", path.name)
                        continue

                    finished_at = datetime.now().isoformat(timespec="seconds")
                    write_import_log(
                        conn,
                        _build_import_log_entry(
                            result,
                            started_at=started_at,
                            finished_at=finished_at,
                            status="success",
                            message="",
                        ),
                    )
                    write_daily_import_registry_entry(
                        conn,
                        file_hash=file_hash,
                        path=path,
                        status="success",
                        result=result,
                    )
                    conn.commit()

                file_record.update(
                    {
                        "status": "imported",
                        "rows_read": int(result.get("rows_read", 0) or 0),
                        "rows_imported": int(result.get("rows_imported", 0) or 0),
                        "rows_replaced": int(result.get("rows_replaced", 0) or 0),
                        "rows_rejected": int(result.get("rows_rejected", 0) or 0),
                        "duplicate_rows": int(result.get("duplicate_rows", 0) or 0),
                        "sales_date_min": str(result.get("sales_date_min", "") or ""),
                        "sales_date_max": str(result.get("sales_date_max", "") or ""),
                        "rejection_reasons": result.get("rejection_reasons", {}),
                    }
                )
                summary["imported"] += 1
                summary["rows_imported"] += int(result.get("rows_imported", 0) or 0)
                summary["rows_replaced"] += int(result.get("rows_replaced", 0) or 0)
                summary["rows_rejected"] += int(result.get("rows_rejected", 0) or 0)
                current_min = str(result.get("sales_date_min", "") or "")
                current_max = str(result.get("sales_date_max", "") or "")
                if current_min and (not summary["date_min"] or current_min < summary["date_min"]):
                    summary["date_min"] = current_min
                if current_max and (not summary["date_max"] or current_max > summary["date_max"]):
                    summary["date_max"] = current_max
                summary["files"].append(file_record)
                logger.info(
                    "Daily sales import success: %s rows_read=%s rows_imported=%s rows_rejected=%s range=%s..%s",
                    path.name,
                    result.get("rows_read", 0),
                    result.get("rows_imported", 0),
                    result.get("rows_rejected", 0),
                    result.get("sales_date_min", ""),
                    result.get("sales_date_max", ""),
                )
    except RuntimeError as exc:
        summary["lock_skipped"] = True
        summary["error"] = str(exc)
        logger.warning("Daily sales scan skipped: %s", exc)

    summary["duration_seconds"] = round(time.perf_counter() - started, 2)
    logger.info(
        "Daily sales scan finished: scanned=%s skipped=%s imported=%s failed=%s rows_imported=%s duration=%.2fs",
        summary["scanned"],
        summary["skipped"],
        summary["imported"],
        summary["failed"],
        summary["rows_imported"],
        summary["duration_seconds"],
    )
    return summary


def import_sales(path: str | Path, batch_size: int = 10000) -> dict[str, int | float | str]:
    with get_db_connection() as conn:
        started_at = datetime.now().isoformat(timespec="seconds")
        try:
            result = import_sales_to_connection(conn, path, batch_size=batch_size, rebuild=True, commit_batches=True)
        except Exception as exc:
            if conn.in_transaction:
                conn.rollback()
            result = _failure_result(path, started_at, exc)
            finished_at = datetime.now().isoformat(timespec="seconds")
            write_import_log(
                conn,
                _build_import_log_entry(result, started_at=started_at, finished_at=finished_at, status="failed", message=str(exc)),
            )
            conn.commit()
            raise
        else:
            finished_at = datetime.now().isoformat(timespec="seconds")
            write_import_log(
                conn,
                _build_import_log_entry(result, started_at=started_at, finished_at=finished_at, status="success", message=""),
            )
            conn.commit()
            return result