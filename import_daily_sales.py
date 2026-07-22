from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from dashboard.builder import rebuild_dashboard_snapshot
from importers.sales_importer import DAILY_EXPORT_DIR, process_daily_sales_folder


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import newly exported daily sales Excel files from exports/sales/daily.")
    parser.add_argument("--input-dir", default=str(DAILY_EXPORT_DIR), help="Daily sales folder to scan")
    parser.add_argument("--batch-size", type=int, default=10000, help="Number of sales rows per database batch")
    parser.add_argument("--json", action="store_true", help="Print the full structured result as JSON")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    started = time.perf_counter()
    result = process_daily_sales_folder(Path(args.input_dir), batch_size=args.batch_size)
    snapshot_result = {"ok": True, "rebuilt": False, "rows": 0, "snapshot_dates": []}
    if int(result.get("imported", 0) or 0) > 0 and not result.get("lock_skipped", False):
        try:
            payload = rebuild_dashboard_snapshot()
            snapshot_result.update({"ok": True, "rebuilt": True, **payload})
        except Exception as exc:
            snapshot_result.update({"ok": False, "rebuilt": True, "error": str(exc)})
    elapsed = time.perf_counter() - started

    print(f"Scanned: {result.get('scanned', 0)}")
    print(f"Skipped duplicate: {result.get('skipped', 0)}")
    print(f"Imported successfully: {result.get('imported', 0)}")
    print(f"Failed: {result.get('failed', 0)}")
    print(f"Sales rows imported: {result.get('rows_imported', 0)}")
    print(f"Rows replaced: {result.get('rows_replaced', 0)}")
    print(f"Rows rejected: {result.get('rows_rejected', 0)}")
    date_min = result.get("date_min") or ""
    date_max = result.get("date_max") or ""
    if date_min or date_max:
        print(f"Date range: {date_min or '--'} to {date_max or '--'}")
    print(f"Snapshot rebuilt: {'yes' if snapshot_result.get('rebuilt') else 'no'}")
    print(f"Elapsed seconds: {elapsed:.2f}")
    if args.json:
        print(json.dumps({"daily_import": result, "snapshot": snapshot_result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()