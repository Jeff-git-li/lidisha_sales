from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config import DB_PATH, DEFAULT_IMAGE_ROOT
from database import get_db_connection


SUPPORTED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


@dataclass(slots=True)
class AssetRecord:
    asset_type: str
    product_code: str
    color_code: str
    storage_provider: str
    storage_key: str
    local_path: str | None
    public_url: str | None
    file_size: int
    last_modified: str
    checksum: str
    imported_at: str
    updated_at: str


def ensure_asset_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS dim_asset (
            asset_id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_type TEXT NOT NULL,
            product_code TEXT NOT NULL,
            color_code TEXT NOT NULL,
            storage_provider TEXT NOT NULL,
            storage_key TEXT NOT NULL,
            local_path TEXT,
            public_url TEXT,
            file_size INTEGER NOT NULL DEFAULT 0,
            last_modified TEXT NOT NULL,
            checksum TEXT NOT NULL,
            imported_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (asset_type, product_code, color_code, storage_provider, storage_key)
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_dim_asset_product_code ON dim_asset(product_code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_dim_asset_storage_provider ON dim_asset(storage_provider)")


def normalize_storage_provider(storage_provider: str | None) -> str:
    provider = (storage_provider or "local").strip().lower()
    if provider not in {"local", "cloudflare_r2", "oss", "s3"}:
        return "local"
    return provider


def build_storage_key(product_code: str, color_code: str, file_name: str) -> str:
    color = str(color_code or "").strip().upper() or "_"
    return f"{str(product_code).strip().upper()}_{color}/{file_name}"


def build_checksum(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def local_public_url(product_code: str, color_code: str) -> str:
    color = str(color_code or "").strip().upper() or "_"
    return f"/product-image/{str(product_code).strip().upper()}/{color}"


def get_product_image(product_code: str, color_code: str | None = None) -> dict[str, Any]:
    query = """
        SELECT asset_type, product_code, color_code, storage_provider, storage_key, local_path, public_url
        FROM dim_asset
        WHERE asset_type = 'product_image' AND product_code = ?
    """
    params: list[Any] = [str(product_code).strip().upper()]
    if color_code is not None:
        query += " AND color_code = ?"
        params.append(str(color_code).strip().upper() or "_")
    query += " ORDER BY updated_at DESC, asset_id DESC LIMIT 1"
    with get_db_connection(DB_PATH) as conn:
        row = conn.execute(query, params).fetchone()
    if not row:
        return {
            "image_url": "",
            "has_image": False,
            "storage_provider": "",
            "storage_key": "",
        }
    image_url = row["public_url"] or (local_public_url(row["product_code"], row["color_code"]) if row["storage_provider"] == "local" else "")
    return {
        "image_url": image_url,
        "has_image": bool(image_url),
        "storage_provider": row["storage_provider"],
        "storage_key": row["storage_key"],
    }


def get_product_assets(product_code: str) -> list[dict[str, Any]]:
    with get_db_connection(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT product_code, color_code, storage_provider, storage_key, public_url
            FROM dim_asset
            WHERE asset_type = 'product_image' AND product_code = ?
            ORDER BY updated_at DESC, asset_id DESC
            """,
            (str(product_code).strip().upper(),),
        ).fetchall()
    assets = []
    for row in rows:
        image_url = row["public_url"] or (local_public_url(row["product_code"], row["color_code"]) if row["storage_provider"] == "local" else "")
        assets.append(
            {
                "product_code": row["product_code"],
                "color_code": row["color_code"],
                "storage_provider": row["storage_provider"],
                "storage_key": row["storage_key"],
                "image_url": image_url,
                "has_image": bool(image_url),
            }
        )
    return assets


def resolve_local_image(root: str | Path, product_code: str, color_code: str | None = None) -> Path | None:
    root_path = Path(root or DEFAULT_IMAGE_ROOT)
    if not root_path.exists():
        return None
    code = str(product_code).strip().upper()
    color = str(color_code or "").strip().upper()
    candidates = []
    if color and color != "_":
        candidates.append(f"{code}_{color}")
    candidates.append(code)
    for candidate in candidates:
        for path in root_path.rglob("*"):
            if path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_EXTS and path.stem.upper() == candidate:
                return path
    return None
