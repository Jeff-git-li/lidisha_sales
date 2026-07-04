from __future__ import annotations

import argparse
import time
from pathlib import Path

from database import get_db_connection
from importers.sales_importer import import_sales


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import retail sales into fact_retail_sales.")
    parser.add_argument("path", type=str, help="Path to the sales Excel file")
    parser.add_argument("--batch-size", type=int, default=10000, help="Number of rows per database batch")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    started = time.perf_counter()
    result = import_sales(args.path, batch_size=args.batch_size)
    with get_db_connection() as conn:
        row_count = conn.execute("SELECT COUNT(*) FROM fact_retail_sales").fetchone()[0]
    elapsed = time.perf_counter() - started
    print(f"rows_read: {result['rows_read']}")
    print(f"rows_imported: {result['rows_imported']}")
    print(f"duplicate_rows: {result['duplicate_rows']}")
    print(f"unknown_products: {result['unknown_products']}")
    print(f"unknown_stores: {result['unknown_stores']}")
    print(f"row_count: {row_count}")
    print(f"load_batch_id: {result['load_batch_id']}")
    print(f"elapsed_seconds: {elapsed:.2f}")


if __name__ == "__main__":
    main()