from __future__ import annotations

import argparse

from importers.inventory_importer import import_inventory_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import inventory snapshot workbook into the retail BI database.")
    parser.add_argument("path", type=str, help="Path to the inventory workbook")
    parser.add_argument("--batch-size", type=int, default=10000, help="Batch size for database upserts")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = import_inventory_file(args.path, batch_size=args.batch_size)
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()