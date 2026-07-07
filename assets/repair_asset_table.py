from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import DB_PATH
from assets.asset_service import ensure_asset_table


def repair_asset_table(db_path: str | Path = DB_PATH) -> None:
    connection = sqlite3.connect(str(db_path), timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA busy_timeout = 30000")
        try:
            connection.execute("DROP TABLE IF EXISTS dim_asset")
            connection.commit()
        except sqlite3.DatabaseError as exc:
            connection.rollback()
            raise RuntimeError(
                f"Unable to drop dim_asset safely: {exc}. The database schema is still malformed and requires manual repair or a restored backup."
            ) from exc

        ensure_asset_table(connection)
        connection.commit()
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Repair the derived dim_asset table")
    parser.add_argument("--db-path", default=DB_PATH, help="SQLite database path")
    args = parser.parse_args()
    repair_asset_table(args.db_path)
    print("dim_asset repaired successfully")


if __name__ == "__main__":
    main()