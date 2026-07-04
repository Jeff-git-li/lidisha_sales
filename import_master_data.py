from __future__ import annotations

import argparse

from importers.master_data_importer import import_master_data, table_counts
from database import get_db_connection


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import normalized master data into the retail BI database.")
    parser.add_argument("--products", type=str, help="Path to 商品.xlsx")
    parser.add_argument("--stores", type=str, help="Path to 商店.xlsx")
    parser.add_argument("--channels", type=str, help="Path to 渠道.xlsx")
    parser.add_argument("--calendar-only", action="store_true", help="Only regenerate dim_calendar")
    parser.add_argument("--calendar-start", type=str, default="2020-01-01", help="Calendar start date in YYYY-MM-DD format")
    parser.add_argument("--calendar-end", type=str, default="2035-12-31", help="Calendar end date in YYYY-MM-DD format")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    import_master_data(
        products=args.products,
        stores=args.stores,
        channels=args.channels,
        calendar_only=args.calendar_only,
        calendar_start=args.calendar_start,
        calendar_end=args.calendar_end,
    )
    with get_db_connection() as conn:
        counts = table_counts(conn)
    for table_name, count in counts.items():
        print(f"{table_name}: {count}")


if __name__ == "__main__":
    main()