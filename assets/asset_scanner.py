from __future__ import annotations

import argparse
import sqlite3
import os
import re
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import DEFAULT_IMAGE_ROOT
from database import get_db_connection

try:
    from .asset_service import (
        build_checksum,
        build_storage_key,
        ensure_asset_table,
        local_public_url,
        normalize_storage_provider,
        resolve_local_image,
    )
except ImportError:
    from assets.asset_service import (  # type: ignore[no-redef]
        build_checksum,
        build_storage_key,
        ensure_asset_table,
        local_public_url,
        normalize_storage_provider,
        resolve_local_image,
    )


SUPPORTED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
FILENAME_RE = re.compile(r"^(?P<product_code>[A-Z0-9]+)_(?P<color_code>[A-Z0-9]+)$", re.IGNORECASE)


def scan_assets(image_root: str = DEFAULT_IMAGE_ROOT, full: bool = False) -> dict[str, int | float]:
    started_at = time.perf_counter()
    indexed_assets = 0
    duplicate_filenames = 0
    invalid_filenames = 0
    asset_rows: list[tuple] = []

    root_path = Path(image_root)
    if not root_path.exists():
        raise FileNotFoundError(f"Image root not found: {root_path}")

    existing_by_key: dict[str, tuple[int, str]] = {}
    if not full:
        with get_db_connection() as conn:
            ensure_asset_table(conn)
            for row in conn.execute(
                """
                SELECT storage_key, file_size, last_modified
                FROM dim_asset
                WHERE asset_type = 'product_image' AND storage_provider = 'local'
                """
            ).fetchall():
                existing_by_key[str(row["storage_key"])] = (int(row["file_size"] or 0), str(row["last_modified"] or ""))

    seen_keys: set[str] = set()
    for dirpath, _, filenames in os.walk(root_path):
        for name in filenames:
            path = Path(dirpath) / name
            if path.suffix.lower() not in SUPPORTED_IMAGE_EXTS:
                continue
            match = FILENAME_RE.match(path.stem)
            if not match:
                invalid_filenames += 1
                continue
            product_code = match.group("product_code").upper()
            color_code = match.group("color_code").upper()
            storage_provider = normalize_storage_provider("local")
            storage_key = build_storage_key(product_code, color_code, path.name)
            if storage_key in seen_keys:
                duplicate_filenames += 1
                continue
            seen_keys.add(storage_key)

            stat = path.stat()
            last_modified = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime))
            checksum = build_checksum(path)
            if not full and existing_by_key.get(storage_key) == (int(stat.st_size), last_modified):
                continue
            asset_rows.append(
                (
                    "product_image",
                    product_code,
                    color_code,
                    storage_provider,
                    storage_key,
                    str(path),
                    local_public_url(product_code, color_code),
                    int(stat.st_size),
                    last_modified,
                    checksum,
                    last_modified,
                    last_modified,
                )
            )
            indexed_assets += 1

    if full:
        try:
            with get_db_connection() as conn:
                ensure_asset_table(conn)
                if asset_rows:
                    conn.executemany(
                        """
                        INSERT INTO dim_asset(
                            asset_type, product_code, color_code, storage_provider, storage_key,
                            local_path, public_url, file_size, last_modified, checksum, imported_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(asset_type, product_code, color_code, storage_provider, storage_key)
                        DO UPDATE SET
                            local_path=excluded.local_path,
                            public_url=excluded.public_url,
                            file_size=excluded.file_size,
                            last_modified=excluded.last_modified,
                            checksum=excluded.checksum,
                            updated_at=excluded.updated_at
                        """,
                        asset_rows,
                    )
                conn.commit()
        except sqlite3.Error as exc:
            raise RuntimeError(f"Unable to write asset index to dim_asset: {exc}") from exc

    total_rows_in_dim_asset = 0
    if full:
        with get_db_connection() as conn:
            ensure_asset_table(conn)
            row = conn.execute("SELECT COUNT(*) AS count FROM dim_asset").fetchone()
            total_rows_in_dim_asset = int(row["count"] if row else 0)
    else:
        total_rows_in_dim_asset = indexed_assets

    elapsed_seconds = round(time.perf_counter() - started_at, 2)
    return {
        "total_rows_in_dim_asset": total_rows_in_dim_asset,
        "indexed_assets": indexed_assets,
        "duplicate_filenames": duplicate_filenames,
        "invalid_filenames": invalid_filenames,
        "elapsed_seconds": elapsed_seconds,
    }


def verify_assets(image_root: str = DEFAULT_IMAGE_ROOT) -> dict[str, int | float]:
    started_at = time.perf_counter()
    root_path = Path(image_root)
    if not root_path.exists():
        raise FileNotFoundError(f"Image root not found: {root_path}")

    indexed_assets = 0
    duplicate_filenames = 0
    invalid_filenames = 0
    seen_keys: set[str] = set()

    for dirpath, _, filenames in os.walk(root_path):
        for name in filenames:
            path = Path(dirpath) / name
            if path.suffix.lower() not in SUPPORTED_IMAGE_EXTS:
                continue
            match = FILENAME_RE.match(path.stem)
            if not match:
                invalid_filenames += 1
                continue
            product_code = match.group("product_code").upper()
            color_code = match.group("color_code").upper()
            storage_key = build_storage_key(product_code, color_code, path.name)
            if storage_key in seen_keys:
                duplicate_filenames += 1
                continue
            seen_keys.add(storage_key)
            indexed_assets += 1

    with get_db_connection() as conn:
        ensure_asset_table(conn)
        dim_asset_rows = int(conn.execute("SELECT COUNT(*) AS count FROM dim_asset").fetchone()["count"])
        db_indexed_assets = int(
            conn.execute(
                "SELECT COUNT(*) AS count FROM dim_asset WHERE asset_type = 'product_image'"
            ).fetchone()["count"]
        )

    elapsed_seconds = round(time.perf_counter() - started_at, 2)
    return {
        "total_rows_in_dim_asset": dim_asset_rows,
        "indexed_assets": db_indexed_assets,
        "duplicate_filenames": duplicate_filenames,
        "invalid_filenames": invalid_filenames,
        "elapsed_seconds": elapsed_seconds,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan product assets into dim_asset")
    parser.add_argument("--full", action="store_true", help="Full scan")
    parser.add_argument("--verify", action="store_true", help="Verify scan only")
    parser.add_argument("--image-root", default=DEFAULT_IMAGE_ROOT, help="Image root folder")
    args = parser.parse_args()

    if args.verify:
        result = verify_assets(args.image_root)
    else:
        result = scan_assets(args.image_root, full=args.full)

    print(f"Total rows in dim_asset: {result['total_rows_in_dim_asset']}")
    print(f"Indexed image count: {result['indexed_assets']}")
    print(f"Invalid filename count: {result['invalid_filenames']}")
    print(f"Duplicate product/color count: {result['duplicate_filenames']}")
    print(f"Elapsed time: {result['elapsed_seconds']}s")


if __name__ == "__main__":
    main()