from __future__ import annotations

from datetime import datetime
from pathlib import Path

from database import get_db_connection
from importers.master_data_importer import rebuild_sales_table, import_sales_file, ensure_import_log_table, write_import_log


def import_sales(path: str | Path, batch_size: int = 10000) -> dict[str, int | float | str]:
    with get_db_connection() as conn:
        rebuild_sales_table(conn)
        ensure_import_log_table(conn)
        started_at = datetime.now().isoformat(timespec="seconds")
        status = "success"
        message = ""
        result: dict[str, int | float | str]
        try:
            result = import_sales_file(conn, path, batch_size=batch_size)
        except Exception as exc:
            status = "failed"
            message = str(exc)
            result = {
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
                "load_batch_id": "",
                "import_run_time": started_at,
            }
            if conn.in_transaction:
                conn.rollback()
            finished_at = datetime.now().isoformat(timespec="seconds")
            write_import_log(
                conn,
                {
                    "load_batch_id": result["load_batch_id"],
                    "import_type": "sales",
                    "source_file": result["source_file"],
                    "started_at": started_at,
                    "finished_at": finished_at,
                    "rows_read": result["rows_read"],
                    "rows_imported": result["rows_imported"],
                    "duplicate_rows": result["duplicate_rows"],
                    "unknown_product_rows": result["unknown_product_rows"],
                    "unknown_product_codes": result["unknown_product_codes"],
                    "unknown_store_rows": result["unknown_store_rows"],
                    "unknown_store_codes": result["unknown_store_codes"],
                    "elapsed_seconds": round((datetime.fromisoformat(finished_at) - datetime.fromisoformat(started_at)).total_seconds(), 2),
                    "status": status,
                    "message": message,
                },
            )
            conn.commit()
            raise
        else:
            finished_at = datetime.now().isoformat(timespec="seconds")
            write_import_log(
                conn,
                {
                    "load_batch_id": result["load_batch_id"],
                    "import_type": "sales",
                    "source_file": result["source_file"],
                    "started_at": started_at,
                    "finished_at": finished_at,
                    "rows_read": result["rows_read"],
                    "rows_imported": result["rows_imported"],
                    "duplicate_rows": result["duplicate_rows"],
                    "unknown_product_rows": result["unknown_product_rows"],
                    "unknown_product_codes": result["unknown_product_codes"],
                    "unknown_store_rows": result["unknown_store_rows"],
                    "unknown_store_codes": result["unknown_store_codes"],
                    "elapsed_seconds": round((datetime.fromisoformat(finished_at) - datetime.fromisoformat(started_at)).total_seconds(), 2),
                    "status": status,
                    "message": message,
                },
            )
            conn.commit()
            return result