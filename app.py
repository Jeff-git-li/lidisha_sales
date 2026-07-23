import argparse
import csv
from datetime import datetime, timedelta
import json
import os
import re
import sqlite3
import time
import sys
from functools import lru_cache
from io import StringIO
from pathlib import Path
import threading

import pandas as pd
from flask import Flask, jsonify, render_template, request, send_file, abort

from config import (
    AUTO_REFRESH_HOUR,
    AUTO_REFRESH_MINUTE,
    DEFAULT_HOST,
    DEFAULT_IMAGE_ROOT,
    DEFAULT_INPUT_DIR,
    DEFAULT_PORT,
    DEFAULT_SEASON_CODE,
    DEFAULT_TOP_N,
    DEFAULT_YEAR_PREFIX,
    IMAGE_INDEX_CACHE_PATH,
    INVENTORY_FILE_GLOB,
    SALES_CSV_GLOB,
    SALES_FILE_GLOB,
    build_app_config,
)
from database import get_db_connection
from importers.sales_importer import process_daily_sales_folder
from logging_config import configure_logging, get_logger
from dashboard.builder import rebuild_dashboard_snapshot
from queries.home import get_home_dashboard
from routes.quarter import quarter_bp
from routes.imports import imports_bp
from routes.insights import insights_bp
from routes.inventory import inventory_bp
from routes.data_center import data_center_bp
from routes.products import products_bp
from routes.regions import regions_bp
from routes.settings import settings_bp
from routes.stores import stores_bp

app = Flask(__name__)
configure_logging()
logger = get_logger(__name__)

app.register_blueprint(products_bp)
app.register_blueprint(stores_bp)
app.register_blueprint(regions_bp)
app.register_blueprint(quarter_bp)
app.register_blueprint(inventory_bp)
app.register_blueprint(data_center_bp)
app.register_blueprint(insights_bp)
app.register_blueprint(imports_bp)
app.register_blueprint(settings_bp)

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
REGION_GROUPS = {
    "全国": [],
    "北区": ["华北", "东北", "西北"],
    "中区": ["华中", "西南", "华东", "河南"],
    "南区": ["华南"],
}
CODE_CATEGORY_MAP = {
    "A": "背心/吊带",
    "B": "裙装",
    "C": "衬衣",
    "D": "大衣",
    "F": "风衣",
    "H": "派克服",
    "J": "马甲",
    "K": "裤装",
    "L": "连衣裙",
    "M": "毛织",
    "N": "牛仔",
    "O": "皮毛外套",
    "P": "包/配饰",
    "S": "赠品",
    "T": "T恤/卫衣",
    "U": "工衣",
    "V": "针织",
    "W": "外套",
    "X": "小衫",
    "Y": "羽绒",
    "Z": "套装",
}
WAVE_LABEL_MAP = {
    "1": "第一波",
    "2": "第二波",
    "3": "第三波",
    "4": "第四波",
    "5": "第五波",
    "6": "第六波",
    "7": "第七波",
    "8": "第八波",
    "9": "第九波",
}
YEAR_PREFIX_MAP = {
    "KP": 2025,
    "KU": 2026,
}
SEASON_CODE_MAP = {
    "1": (1, "春季"),
    "2": (2, "夏季"),
    "3": (3, "秋季"),
    "4": (4, "冬季"),
}
EXCLUDED_CATEGORY_CODES = {"P", "S"}

DATA = None
INVENTORY_DATA = None
IMAGE_INDEX = {}
IMAGE_INDEX_READY = False
IMAGE_INDEX_THREAD = None
AUTO_REFRESH_THREAD = None
DATA_REFRESH_LOCK = threading.Lock()
EXPORT_DATE_RE = re.compile(r"(20\d{2}-\d{2}-\d{2})")
APP_CONFIG = build_app_config()


def find_header_row(excel_path: str, sheet_name=0) -> int:
    probe = pd.read_excel(excel_path, sheet_name=sheet_name, header=None, nrows=80)
    required = {"商品代码", "区域名称", "数量"}
    for i, row in probe.iterrows():
        values = {str(x).strip() for x in row.dropna().tolist()}
        if required.issubset(values):
            return int(i)
    raise ValueError("没有找到包含 商品代码 / 区域名称 / 数量 的表头行")


def infer_category(code: str) -> str:
    code = str(code).strip().upper()
    m = re.match(r"^[A-Z]+\d{2}([A-Z])", code)
    if m:
        return CODE_CATEGORY_MAP.get(m.group(1), f"其他-{m.group(1)}")
    return "其他"


def include_product_code(code: str) -> bool:
    code = str(code).strip().upper()
    if not code.startswith("K"):
        return False
    match = re.match(r"^[A-Z]+\d{2}([A-Z])", code)
    return not (match and match.group(1) in EXCLUDED_CATEGORY_CODES)


def clean_text_value(value) -> str:
    text = "" if pd.isna(value) else str(value).strip()
    if text.startswith('="') and text.endswith('"'):
        text = text[2:-1]
    elif text.startswith('="'):
        text = text[2:]
    elif text.startswith('='):
        text = text[1:]
    return text.strip()


def series_or_default(df: pd.DataFrame, column: str, default_value="") -> pd.Series:
    if column in df.columns:
        return df[column]
    return pd.Series([default_value] * len(df), index=df.index)


def read_sales_csv_file(csv_path: str) -> pd.DataFrame:
    required_columns = {"款号", "零售数量"}
    attempts = []
    raw_bytes = Path(csv_path).read_bytes()
    for encoding in ("utf-8-sig", "gb18030", "utf-8"):
        try:
            decoded_text = raw_bytes.decode(encoding)
        except Exception as exc:
            attempts.append(f"{encoding}: {exc}")
            continue
        sample = decoded_text[:4096]
        tab_count = sample.count("\t")
        comma_count = sample.count(",")
        semicolon_count = sample.count(";")
        if tab_count > 0 and tab_count >= comma_count and tab_count >= semicolon_count:
            separator = "\t"
        elif comma_count > 0 and comma_count >= semicolon_count:
            separator = ","
        elif semicolon_count > 0:
            separator = ";"
        else:
            separator = ","

        try:
            if separator == "\t":
                physical_rows = list(csv.reader(StringIO(decoded_text), delimiter=",", quotechar='"'))
                normalized_rows = []
                for row in physical_rows:
                    if not row:
                        continue
                    first_cell = str(row[0]).strip()
                    if not first_cell:
                        continue
                    normalized_rows.append([str(part).strip() for part in first_cell.split("\t")])
                rows = normalized_rows
                if not rows:
                    raise ValueError("CSV为空")
                header = [str(column).strip() for column in rows[0]]
                data_rows = [row for row in rows[1:] if len(row) == len(header)]
                df = pd.DataFrame(data_rows, columns=header, dtype=str)
            else:
                df = pd.read_csv(StringIO(decoded_text), dtype=str, sep=separator, engine="python")
        except Exception as exc:
            attempts.append(f"{encoding}/{separator}: {exc}")
            continue

        df.columns = [str(c).strip() for c in df.columns]
        if required_columns.issubset(df.columns):
            return df
        attempts.append(f"{encoding}/{separator}: 缺少必要列 {sorted(required_columns - set(df.columns))}")
    raise ValueError(f"无法读取CSV文件: {csv_path}; 尝试结果: {' | '.join(attempts)}")


def infer_export_date(excel_path: str) -> pd.Timestamp:
    match = EXPORT_DATE_RE.search(Path(excel_path).stem)
    if match:
        parsed = pd.to_datetime(match.group(1), errors="coerce")
        if not pd.isna(parsed):
            return parsed.normalize()
    return pd.to_datetime(Path(excel_path).stat().st_mtime, unit="s").normalize()


def infer_season(code: str) -> tuple[str, int | None, str, str]:
    code = str(code).strip().upper()
    if len(code) < 3:
        return "", None, "", "未识别季节"
    year_prefix = code[:2]
    year = YEAR_PREFIX_MAP.get(year_prefix)
    season_info = SEASON_CODE_MAP.get(code[2])
    if year and season_info:
        season_order, season_name = season_info
        return year_prefix, season_order, code[2], f"{year}{season_name}"
    return year_prefix, None, code[2] if len(code) >= 3 else "", "未识别季节"


def infer_wave(code: str) -> str:
    code = str(code).strip().upper()
    if len(code) < 4:
        return "未知波段"
    return WAVE_LABEL_MAP.get(code[3], "未知波段")


def enrich_season_columns(df: pd.DataFrame) -> pd.DataFrame:
    season_info = df["商品代码"].apply(infer_season)
    df["年份代号"] = season_info.apply(lambda item: item[0])
    df["年份"] = season_info.apply(lambda item: YEAR_PREFIX_MAP.get(item[0]))
    df["季节序"] = season_info.apply(lambda item: item[1])
    df["季节代号"] = season_info.apply(lambda item: item[2])
    df["季节"] = season_info.apply(lambda item: item[3])
    df["波段"] = df["商品代码"].apply(infer_wave)
    return df


def season_sort_key(season_label: str) -> tuple[int, int]:
    match = re.match(r"^(\d{4})(春季|夏季|秋季|冬季)$", str(season_label))
    order_map = {"春季": 1, "夏季": 2, "秋季": 3, "冬季": 4}
    if match:
        return int(match.group(1)), order_map[match.group(2)]
    return (0, 0)


def year_option_rows(df: pd.DataFrame) -> list[dict]:
    options = []
    seen = set()
    for prefix, year in YEAR_PREFIX_MAP.items():
        if prefix in df.get("年份代号", pd.Series(dtype=str)).dropna().unique().tolist() or prefix == DEFAULT_YEAR_PREFIX:
            seen.add(prefix)
            options.append({"value": prefix, "label": f"{year}" if year else prefix})
    for prefix in df.get("年份代号", pd.Series(dtype=str)).dropna().unique().tolist():
        if prefix and prefix not in seen:
            year = YEAR_PREFIX_MAP.get(prefix)
            options.append({"value": prefix, "label": f"{year}" if year else prefix})
    return options


def season_option_rows() -> list[dict]:
    return [
        {"value": code, "label": f"{code}({name})"}
        for code, (_, name) in sorted(SEASON_CODE_MAP.items(), key=lambda item: int(item[0]))
    ]


def wave_sort_key(label: str) -> tuple[int, str]:
    for digit, wave_label in WAVE_LABEL_MAP.items():
        if label == wave_label:
            return int(digit), label
    return (99, str(label))


def wave_option_rows(df: pd.DataFrame) -> list[dict]:
    if "波段" not in df.columns:
        return []
    values = sorted(df["波段"].dropna().astype(str).unique().tolist(), key=wave_sort_key)
    return [{"value": value, "label": value} for value in values if value]


def load_sales(excel_path: str) -> pd.DataFrame:
    header_row = find_header_row(excel_path)
    df = pd.read_excel(excel_path, header=header_row)
    df.columns = [str(c).strip() for c in df.columns]
    keep = [c for c in ["商品代码", "商品名称", "颜色名称", "颜色代码", "选定价", "区域名称", "商店名称", "日期", "数量"] if c in df.columns]
    df = df[keep].copy()
    df = df[df["商品代码"].notna() & df["区域名称"].notna() & df["数量"].notna()]
    df["商品代码"] = df["商品代码"].astype(str).str.strip()
    df = df[df["商品代码"].apply(include_product_code)]
    df["颜色代码"] = series_or_default(df, "颜色代码").astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
    df["颜色名称"] = series_or_default(df, "颜色名称").fillna("").astype(str).str.strip()
    df["选定价"] = pd.to_numeric(series_or_default(df, "选定价", 0), errors="coerce").fillna(0)
    df["数量"] = pd.to_numeric(df["数量"], errors="coerce").fillna(0)
    df["区域名称"] = df["区域名称"].astype(str).str.strip()
    if "商品名称" not in df.columns:
        df["商品名称"] = df["商品代码"].apply(infer_category)
    else:
        df["商品名称"] = df["商品名称"].fillna("").astype(str).str.strip()
        df.loc[df["商品名称"].eq(""), "商品名称"] = df.loc[df["商品名称"].eq(""), "商品代码"].apply(infer_category)
    inferred_date = infer_export_date(excel_path)
    if "日期" in df.columns:
        df["日期"] = pd.to_datetime(df["日期"], errors="coerce").fillna(inferred_date).dt.normalize()
    else:
        df["日期"] = inferred_date
    if "商店名称" in df.columns:
        df["商店名称"] = df["商店名称"].fillna("").astype(str).str.strip()
        df.loc[df["商店名称"].eq(""), "商店名称"] = "未提供商店"
    else:
        df["商店名称"] = "未提供商店"
    df = enrich_season_columns(df)
    df["品类"] = df["商品代码"].apply(infer_category)
    df["销售额"] = df["数量"] * df["选定价"]
    return df


def load_sales_csv(csv_path: str) -> pd.DataFrame:
    df = read_sales_csv_file(csv_path)
    keep_map = {
        "店仓名称": "商店名称",
        "款号": "商品代码",
        "条码.颜色": "颜色名称",
        "单据日期.日期": "日期",
        "零售数量": "数量",
        "吊牌金额": "选定价",
        "成交金额": "销售额",
    }
    available = [source for source in keep_map if source in df.columns]
    df = df[available].rename(columns=keep_map).copy()
    if "商品代码" not in df.columns or "数量" not in df.columns:
        raise ValueError(f"CSV缺少必要列: {csv_path}")

    for column in ["商品代码", "商店名称", "颜色名称", "日期", "数量", "选定价", "销售额"]:
        if column in df.columns:
            df[column] = df[column].map(clean_text_value)

    df["商品代码"] = df["商品代码"].fillna("").astype(str).str.strip().str.upper()
    if "颜色名称" in df.columns:
        df["颜色名称"] = df["颜色名称"].fillna("").astype(str).str.strip()

    df = df[df["商品代码"].apply(include_product_code)]

    if "商店名称" in df.columns:
        df["商店名称"] = df["商店名称"].fillna("").astype(str).str.strip()
        df.loc[df["商店名称"].eq(""), "商店名称"] = "未提供商店"
    else:
        df["商店名称"] = "未提供商店"

    df["区域名称"] = "河南"
    if "颜色名称" in df.columns:
        df["颜色名称"] = df["颜色名称"].fillna("").astype(str).str.strip()
        df.loc[df["颜色名称"].eq(""), "颜色名称"] = "未提供颜色"
    else:
        df["颜色名称"] = "未提供颜色"

    inventory_exact_lookup, inventory_fallback_lookup = inventory_color_lookups()
    sales_exact_lookup, sales_fallback_lookup = sales_color_lookups()
    df["颜色代码"] = [
        inventory_exact_lookup.get(
            (code, color_name),
            sales_exact_lookup.get(
                (code, color_name),
                inventory_fallback_lookup.get(code, sales_fallback_lookup.get(code, "")),
            ),
        )
        for code, color_name in zip(df["商品代码"], df["颜色名称"])
    ]
    df["颜色代码"] = pd.Series(df["颜色代码"], index=df.index).fillna("").astype(str).str.strip()

    df["选定价"] = pd.to_numeric(series_or_default(df, "选定价", 0), errors="coerce").fillna(0)
    df["数量"] = pd.to_numeric(df["数量"], errors="coerce").fillna(0)
    if "销售额" in df.columns:
        df["销售额"] = pd.to_numeric(df["销售额"], errors="coerce").fillna(0)
    else:
        df["销售额"] = df["数量"] * df["选定价"]

    df["商品名称"] = df["商品代码"].apply(infer_category)
    if "日期" in df.columns:
        df["日期"] = pd.to_datetime(df["日期"], format="%Y%m%d", errors="coerce").dt.normalize()
    else:
        df["日期"] = pd.NaT
    df["日期"] = df["日期"].fillna(infer_export_date(csv_path))

    df = enrich_season_columns(df)
    df["品类"] = df["商品代码"].apply(infer_category)
    return df


def find_inventory_header_row(excel_path: str, sheet_name=0) -> int:
    probe = pd.read_excel(excel_path, sheet_name=sheet_name, header=None, nrows=80)
    required = {"商品代码", "颜色代码", "数量"}
    for i, row in probe.iterrows():
        values = {str(x).strip() for x in row.dropna().tolist()}
        if required.issubset(values):
            return int(i)
    raise ValueError("没有找到包含 商品代码 / 颜色代码 / 数量 的进货表头行")


def load_inventory(excel_path: str) -> pd.DataFrame:
    header_row = find_inventory_header_row(excel_path)
    df = pd.read_excel(excel_path, header=header_row)
    df.columns = [str(c).strip() for c in df.columns]
    keep = [c for c in ["商品代码", "商品名称", "颜色名称", "颜色代码", "选定价", "数量"] if c in df.columns]
    df = df[keep].copy()
    df = df[df["商品代码"].notna() & df["数量"].notna()]
    df["商品代码"] = df["商品代码"].astype(str).str.strip()
    df = df[df["商品代码"].apply(include_product_code)]
    if "商品名称" in df.columns:
        df["商品名称"] = df["商品名称"].fillna("").astype(str).str.strip()
        df.loc[df["商品名称"].eq(""), "商品名称"] = df.loc[df["商品名称"].eq(""), "商品代码"]
    else:
        df["商品名称"] = df["商品代码"]
    df["颜色代码"] = series_or_default(df, "颜色代码").astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
    df["颜色名称"] = series_or_default(df, "颜色名称").fillna("").astype(str).str.strip()
    df["选定价"] = pd.to_numeric(series_or_default(df, "选定价", 0), errors="coerce").fillna(0)
    df["数量"] = pd.to_numeric(df["数量"], errors="coerce").fillna(0)
    df = enrich_season_columns(df)
    df["品类"] = df["商品代码"].apply(infer_category)
    return df


def build_color_lookups(df: pd.DataFrame) -> tuple[dict, dict]:
    if df.empty:
        return {}, {}

    lookup_df = df[["商品代码", "颜色名称", "颜色代码"]].copy()
    lookup_df["商品代码"] = lookup_df["商品代码"].fillna("").astype(str).str.strip().str.upper()
    lookup_df["颜色名称"] = lookup_df["颜色名称"].fillna("").astype(str).str.strip()
    lookup_df["颜色代码"] = lookup_df["颜色代码"].fillna("").astype(str).str.strip()
    lookup_df = lookup_df[lookup_df["商品代码"].ne("")]

    exact_df = lookup_df[lookup_df["颜色名称"].ne("") & lookup_df["颜色代码"].ne("")]
    exact_df = exact_df.drop_duplicates(subset=["商品代码", "颜色名称"], keep="first")
    exact_lookup = {
        (row["商品代码"], row["颜色名称"]): row["颜色代码"]
        for _, row in exact_df.iterrows()
    }

    unique_color_counts = lookup_df[lookup_df["颜色代码"].ne("")].groupby("商品代码")["颜色代码"].nunique()
    single_color_codes = lookup_df[lookup_df["颜色代码"].ne("")].drop_duplicates(subset=["商品代码", "颜色代码"], keep="first")
    fallback_lookup = {
        row["商品代码"]: row["颜色代码"]
        for _, row in single_color_codes.iterrows()
        if unique_color_counts.get(row["商品代码"], 0) == 1
    }
    return exact_lookup, fallback_lookup


@lru_cache(maxsize=1)
def inventory_color_lookup_cache(inventory_path: str, file_mtime: float) -> tuple[dict, dict]:
    df = load_inventory(inventory_path)
    return build_color_lookups(df)


def inventory_color_lookups() -> tuple[dict, dict]:
    inventory_path = APP_CONFIG.get("inventory_path")
    if not inventory_path:
        try:
            inventory_path = latest_matching_excel(APP_CONFIG["input_dir"], INVENTORY_FILE_GLOB)
        except FileNotFoundError:
            return {}, {}
    file_mtime = os.path.getmtime(inventory_path)
    return inventory_color_lookup_cache(inventory_path, file_mtime)


@lru_cache(maxsize=1)
def sales_color_lookup_cache(source_paths_key: tuple[str, ...], mtimes_key: tuple[float, ...]) -> tuple[dict, dict]:
    frames = [load_sales(path) for path in source_paths_key if str(path).lower().endswith(".xlsx")]
    if not frames:
        return {}, {}
    return build_color_lookups(pd.concat(frames, ignore_index=True))


def sales_color_lookups() -> tuple[dict, dict]:
    if APP_CONFIG.get("excel_path"):
        source_paths = [APP_CONFIG["excel_path"]]
    else:
        source_paths = [path for path in sales_source_files(APP_CONFIG["input_dir"]) if str(path).lower().endswith(".xlsx")]
    if not source_paths:
        return {}, {}
    resolved = [str(Path(path).resolve()) for path in source_paths]
    mtimes = [Path(path).stat().st_mtime for path in resolved]
    return sales_color_lookup_cache(tuple(resolved), tuple(mtimes))


def clear_import_tables(conn: sqlite3.Connection):
    conn.execute("DELETE FROM sales_daily")
    conn.execute("DELETE FROM imports")
    conn.execute("DELETE FROM products")
    conn.execute("DELETE FROM product_colors")
    conn.execute("DELETE FROM stores")


def normalize_key(code, color):
    return f"{str(code).strip().upper()}_{str(color).strip().upper()}"


def build_image_index(root: str) -> dict:
    if IMAGE_INDEX_CACHE_PATH.exists():
        try:
            cached = json.loads(IMAGE_INDEX_CACHE_PATH.read_text(encoding="utf-8"))
            if isinstance(cached, dict) and cached:
                return cached
        except Exception:
            pass

    index = {}
    root_path = Path(root)
    if not root or not root_path.exists():
        return index
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            suffix = Path(name).suffix.lower()
            if suffix in IMAGE_EXTS:
                stem = Path(name).stem.upper()
                if "_" in stem and stem not in index:
                    index[stem] = str(Path(dirpath) / name)
    try:
        IMAGE_INDEX_CACHE_PATH.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return index


def init_db(conn: sqlite3.Connection):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS imports (
            file_path TEXT PRIMARY KEY,
            file_mtime REAL NOT NULL,
            imported_at TEXT NOT NULL,
            row_count INTEGER NOT NULL,
            start_date TEXT,
            end_date TEXT
        );

        CREATE TABLE IF NOT EXISTS products (
            product_code TEXT PRIMARY KEY,
            product_name TEXT,
            category TEXT
        );

        CREATE TABLE IF NOT EXISTS product_colors (
            product_code TEXT NOT NULL,
            color_code TEXT NOT NULL,
            color_name TEXT,
            PRIMARY KEY (product_code, color_code)
        );

        CREATE TABLE IF NOT EXISTS stores (
            store_name TEXT PRIMARY KEY,
            region_name TEXT
        );

        CREATE TABLE IF NOT EXISTS sales_daily (
            sale_date TEXT NOT NULL,
            store_name TEXT NOT NULL,
            product_code TEXT NOT NULL,
            color_code TEXT NOT NULL,
            selected_price REAL NOT NULL,
            quantity REAL NOT NULL,
            amount REAL NOT NULL,
            source_file TEXT NOT NULL,
            PRIMARY KEY (sale_date, store_name, product_code, color_code)
        );

        CREATE INDEX IF NOT EXISTS idx_sales_daily_date ON sales_daily(sale_date);
        CREATE INDEX IF NOT EXISTS idx_sales_daily_store ON sales_daily(store_name);
        CREATE INDEX IF NOT EXISTS idx_sales_daily_product ON sales_daily(product_code);
        """
    )


def list_excel_files(input_dir: str, pattern: str = "*.xlsx") -> list[str]:
    folder = Path(input_dir)
    files = [p for p in folder.glob(pattern) if not p.name.startswith("~$")]
    if not files:
        raise FileNotFoundError(f"目录中没有找到匹配文件: {input_dir} / {pattern}")
    return [str(p) for p in sorted(files, key=lambda item: item.stat().st_mtime)]


def latest_matching_excel(input_dir: str, pattern: str) -> str:
    return list_excel_files(input_dir, pattern)[-1]


def sales_source_files(input_dir: str) -> list[str]:
    files = list_excel_files(input_dir, SALES_FILE_GLOB) + list_excel_files(input_dir, SALES_CSV_GLOB)
    unique_files = sorted({str(Path(path).resolve()) for path in files}, key=lambda item: Path(item).stat().st_mtime)
    return unique_files


def aggregate_import_rows(df: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        df.groupby(["日期", "商店名称", "区域名称", "商品代码", "颜色代码"], as_index=False)
        .agg(
            商品名称=("商品名称", "first"),
            颜色名称=("颜色名称", "first"),
            品类=("品类", "first"),
            选定价=("选定价", "max"),
            数量=("数量", "sum"),
            销售额=("销售额", "sum"),
        )
    )
    grouped["日期"] = pd.to_datetime(grouped["日期"], errors="coerce").dt.strftime("%Y-%m-%d")
    return grouped


def import_sales_file(conn: sqlite3.Connection, excel_path: str):
    file_path = str(Path(excel_path).resolve())
    file_mtime = Path(excel_path).stat().st_mtime
    imported = conn.execute("SELECT file_mtime FROM imports WHERE file_path = ?", (file_path,)).fetchone()
    if imported and float(imported["file_mtime"]) == float(file_mtime):
        return

    df = aggregate_import_rows(load_sales(excel_path))
    conn.execute("DELETE FROM sales_daily WHERE source_file = ?", (file_path,))

    products = df[["商品代码", "商品名称", "品类"]].drop_duplicates().itertuples(index=False, name=None)
    conn.executemany(
        "INSERT INTO products(product_code, product_name, category) VALUES (?, ?, ?) ON CONFLICT(product_code) DO UPDATE SET product_name=excluded.product_name, category=excluded.category",
        list(products),
    )

    product_colors = df[["商品代码", "颜色代码", "颜色名称"]].drop_duplicates().itertuples(index=False, name=None)
    conn.executemany(
        "INSERT INTO product_colors(product_code, color_code, color_name) VALUES (?, ?, ?) ON CONFLICT(product_code, color_code) DO UPDATE SET color_name=excluded.color_name",
        list(product_colors),
    )

    stores = df[["商店名称", "区域名称"]].drop_duplicates().itertuples(index=False, name=None)
    conn.executemany(
        "INSERT INTO stores(store_name, region_name) VALUES (?, ?) ON CONFLICT(store_name) DO UPDATE SET region_name=excluded.region_name",
        list(stores),
    )

    facts = [
        (
            row["日期"],
            row["商店名称"],
            row["商品代码"],
            row["颜色代码"],
            float(row["选定价"]),
            float(row["数量"]),
            float(row["销售额"]),
            file_path,
        )
        for _, row in df.iterrows()
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO sales_daily(sale_date, store_name, product_code, color_code, selected_price, quantity, amount, source_file) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        facts,
    )

    start_date = df["日期"].min() if not df.empty else None
    end_date = df["日期"].max() if not df.empty else None
    conn.execute(
        "INSERT OR REPLACE INTO imports(file_path, file_mtime, imported_at, row_count, start_date, end_date) VALUES (?, ?, ?, ?, ?, ?)",
        (file_path, file_mtime, time.strftime("%Y-%m-%d %H:%M:%S"), len(df), start_date, end_date),
    )


def import_sales_data(conn: sqlite3.Connection, source_path: str):
    if Path(source_path).suffix.lower() == ".csv":
        df = aggregate_import_rows(load_sales_csv(source_path))
    else:
        df = aggregate_import_rows(load_sales(source_path))

    file_path = str(Path(source_path).resolve())
    file_mtime = Path(source_path).stat().st_mtime
    imported = conn.execute("SELECT file_mtime FROM imports WHERE file_path = ?", (file_path,)).fetchone()
    if imported and float(imported["file_mtime"]) == float(file_mtime):
        return

    conn.execute("DELETE FROM sales_daily WHERE source_file = ?", (file_path,))

    products = df[["商品代码", "商品名称", "品类"]].drop_duplicates().itertuples(index=False, name=None)
    conn.executemany(
        "INSERT INTO products(product_code, product_name, category) VALUES (?, ?, ?) ON CONFLICT(product_code) DO UPDATE SET product_name=excluded.product_name, category=excluded.category",
        list(products),
    )

    product_colors = df[["商品代码", "颜色代码", "颜色名称"]].drop_duplicates().itertuples(index=False, name=None)
    conn.executemany(
        "INSERT INTO product_colors(product_code, color_code, color_name) VALUES (?, ?, ?) ON CONFLICT(product_code, color_code) DO UPDATE SET color_name=excluded.color_name",
        list(product_colors),
    )

    stores = df[["商店名称", "区域名称"]].drop_duplicates().itertuples(index=False, name=None)
    conn.executemany(
        "INSERT INTO stores(store_name, region_name) VALUES (?, ?) ON CONFLICT(store_name) DO UPDATE SET region_name=excluded.region_name",
        list(stores),
    )

    facts = [
        (
            row["日期"],
            row["商店名称"],
            row["商品代码"],
            row["颜色代码"],
            float(row["选定价"]),
            float(row["数量"]),
            float(row["销售额"]),
            file_path,
        )
        for _, row in df.iterrows()
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO sales_daily(sale_date, store_name, product_code, color_code, selected_price, quantity, amount, source_file) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        facts,
    )

    start_date = df["日期"].min() if not df.empty else None
    end_date = df["日期"].max() if not df.empty else None
    conn.execute(
        "INSERT OR REPLACE INTO imports(file_path, file_mtime, imported_at, row_count, start_date, end_date) VALUES (?, ?, ?, ?, ?, ?)",
        (file_path, file_mtime, time.strftime("%Y-%m-%d %H:%M:%S"), len(df), start_date, end_date),
    )


def load_sales_from_db(conn: sqlite3.Connection) -> pd.DataFrame:
    query = """
        SELECT
            sd.sale_date AS 日期,
            sd.store_name AS 商店名称,
            COALESCE(st.region_name, '未提供区域') AS 区域名称,
            sd.product_code AS 商品代码,
            COALESCE(p.product_name, sd.product_code) AS 商品名称,
            COALESCE(pc.color_name, '') AS 颜色名称,
            sd.color_code AS 颜色代码,
            sd.selected_price AS 选定价,
            sd.quantity AS 数量,
            COALESCE(p.category, '其他') AS 品类,
            sd.amount AS 销售额
        FROM sales_daily sd
        LEFT JOIN products p ON p.product_code = sd.product_code
        LEFT JOIN product_colors pc ON pc.product_code = sd.product_code AND pc.color_code = sd.color_code
        LEFT JOIN stores st ON st.store_name = sd.store_name
    """
    df = pd.read_sql_query(query, conn)
    if df.empty:
        return df
    df["日期"] = pd.to_datetime(df["日期"], errors="coerce").dt.normalize()
    df["选定价"] = pd.to_numeric(df["选定价"], errors="coerce").fillna(0)
    df["数量"] = pd.to_numeric(df["数量"], errors="coerce").fillna(0)
    df["销售额"] = pd.to_numeric(df["销售额"], errors="coerce").fillna(0)
    df = enrich_season_columns(df)
    return df


def refresh_sales_data() -> pd.DataFrame:
    with get_db_connection() as conn:
        init_db(conn)
        clear_import_tables(conn)
        if APP_CONFIG.get("excel_path"):
            import_sales_data(conn, APP_CONFIG["excel_path"])
        else:
            for source_path in sales_source_files(APP_CONFIG["input_dir"]):
                import_sales_data(conn, source_path)
        conn.commit()
        return load_sales_from_db(conn)


def refresh_inventory_data() -> pd.DataFrame:
    inventory_path = APP_CONFIG.get("inventory_path")
    if not inventory_path:
        try:
            inventory_path = latest_matching_excel(APP_CONFIG["input_dir"], INVENTORY_FILE_GLOB)
        except FileNotFoundError:
            return pd.DataFrame(columns=["商品代码", "商品名称", "颜色名称", "颜色代码", "选定价", "数量", "品类", "年份代号", "年份", "季节序", "季节代号", "季节"])
    return load_inventory(inventory_path)


def start_image_index_build(root: str):
    global IMAGE_INDEX_READY, IMAGE_INDEX_THREAD
    IMAGE_INDEX_READY = False

    def worker():
        global IMAGE_INDEX, IMAGE_INDEX_READY
        IMAGE_INDEX = build_image_index(root)
        IMAGE_INDEX_READY = True

    IMAGE_INDEX_THREAD = threading.Thread(target=worker, daemon=True)
    IMAGE_INDEX_THREAD.start()


def _sales_row_count() -> int:
    with get_db_connection() as conn:
        try:
            row = conn.execute("SELECT COUNT(*) AS row_count FROM fact_retail_sales").fetchone()
        except sqlite3.OperationalError:
            return 0
    return int(row["row_count"] or 0) if row else 0


def _snapshot_needs_rebuild() -> bool:
    with get_db_connection() as conn:
        try:
            row = conn.execute("SELECT COUNT(*) AS row_count FROM dashboard_snapshot").fetchone()
        except sqlite3.OperationalError:
            return True
    return not row or int(row["row_count"] or 0) == 0


def _ensure_image_index_started() -> None:
    if IMAGE_INDEX or IMAGE_INDEX_READY:
        return
    if IMAGE_INDEX_THREAD and IMAGE_INDEX_THREAD.is_alive():
        return
    start_image_index_build(APP_CONFIG["image_root"])
    resolve_image_path.cache_clear()


def _should_run_reloader_worker(reloader_enabled: bool) -> bool:
    if not reloader_enabled:
        return True
    return os.environ.get("WERKZEUG_RUN_MAIN") == "true"


def reload_dashboard_data(trigger: str = "manual") -> dict:
    global DATA, INVENTORY_DATA
    with DATA_REFRESH_LOCK:
        daily_import = process_daily_sales_folder(Path(APP_CONFIG["input_dir"]) / "sales" / "daily")
        INVENTORY_DATA = refresh_inventory_data()
        DATA = pd.DataFrame()
        snapshot_result = {
            "ok": True,
            "rebuilt": False,
            "rows": 0,
            "snapshot_dates": [],
            "error": "",
        }
        should_rebuild_snapshot = (
            not daily_import.get("lock_skipped", False)
            and (
                int(daily_import.get("imported", 0) or 0) > 0
                or _snapshot_needs_rebuild()
            )
        )
        if should_rebuild_snapshot:
            try:
                snapshot_payload = rebuild_dashboard_snapshot()
                snapshot_result.update({"ok": True, "rebuilt": True, **snapshot_payload})
            except Exception as exc:
                logger.exception("快照重建失败：%s", exc)
                snapshot_result.update({"ok": False, "rebuilt": True, "error": str(exc)})
        elif daily_import.get("lock_skipped", False):
            snapshot_result.update({"ok": False, "error": str(daily_import.get("error", "")), "skipped": True})
        else:
            snapshot_result.update({"skipped": True})
        if trigger == "startup":
            _ensure_image_index_started()
        row_count = _sales_row_count()
        return {
            "trigger": trigger,
            "rows": row_count,
            "images": len(IMAGE_INDEX),
            "image_index_ready": IMAGE_INDEX_READY,
            "snapshot_rows": snapshot_result.get("rows", 0),
            "snapshot_dates": snapshot_result.get("snapshot_dates", []),
            "daily_import": daily_import,
            "snapshot": snapshot_result,
            "loaded_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }


def next_auto_refresh_time(now: datetime | None = None) -> datetime:
    now = now or datetime.now()
    target = now.replace(hour=AUTO_REFRESH_HOUR, minute=AUTO_REFRESH_MINUTE, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


def auto_refresh_loop():
    while True:
        run_at = next_auto_refresh_time()
        wait_seconds = max(1.0, (run_at - datetime.now()).total_seconds())
        time.sleep(wait_seconds)
        try:
            result = reload_dashboard_data(trigger="scheduled")
            logger.info(
                "[%s] 每日自动刷新完成：rows=%s imported=%s skipped=%s failed=%s snapshot_ok=%s",
                result["loaded_at"],
                f"{result['rows']:,}",
                result.get("daily_import", {}).get("imported", 0),
                result.get("daily_import", {}).get("skipped", 0),
                result.get("daily_import", {}).get("failed", 0),
                result.get("snapshot", {}).get("ok", True),
            )
        except Exception as exc:
            logger.exception("[%s] 每日自动刷新失败：%s", time.strftime("%Y-%m-%d %H:%M:%S"), exc)


def start_auto_refresh_scheduler(reloader_enabled: bool = False):
    global AUTO_REFRESH_THREAD
    if not _should_run_reloader_worker(reloader_enabled):
        logger.info("已跳过开发模式父进程自动刷新调度器")
        return
    if AUTO_REFRESH_THREAD and AUTO_REFRESH_THREAD.is_alive():
        return
    AUTO_REFRESH_THREAD = threading.Thread(target=auto_refresh_loop, name="daily-auto-refresh", daemon=True)
    AUTO_REFRESH_THREAD.start()
    next_run = next_auto_refresh_time().strftime("%Y-%m-%d %H:%M:%S")
    logger.info("已启用每日自动刷新：每天 %02d:%02d，下次执行 %s", AUTO_REFRESH_HOUR, AUTO_REFRESH_MINUTE, next_run)


@lru_cache(maxsize=8192)
def resolve_image_path(root: str, code: str, color: str) -> str | None:
    root_path = Path(root)
    if not root or not root_path.exists():
        return None

    code = str(code).strip().upper()
    color = str(color).strip().upper()
    if not code:
        return None

    candidates = []
    if color and color != "_":
        candidates.append(f"{code}_{color}")
    candidates.append(code)

    for candidate in candidates:
        for suffix in IMAGE_EXTS:
            for path in root_path.rglob(f"{candidate}{suffix}"):
                if path.is_file():
                    return str(path)
    return None


def agg_rank(df: pd.DataFrame, group_cols, top_n=20, region_filter=None, category=None):
    sub = df.copy()
    if region_filter:
        sub = sub[sub["区域名称"].isin(region_filter)]
    if category:
        sub = sub[sub["品类"].eq(category)]
    if sub.empty:
        return []
    agg = (
        sub.groupby(group_cols, as_index=False)
        .agg(销量=("数量", "sum"), 销售额=("销售额", "sum"), 选定价=("选定价", "max"))
        .sort_values(["销量", "销售额"], ascending=False)
        .head(int(top_n))
    )
    agg.insert(0, "排名", range(1, len(agg) + 1))
    rows = agg.to_dict(orient="records")
    for r in rows:
        r["销量"] = int(round(r.get("销量", 0)))
        r["销售额"] = round(float(r.get("销售额", 0)), 2)
        r["选定价"] = round(float(r.get("选定价", 0)), 2)
        code = r.get("商品代码", "")
        color = r.get("颜色代码", "")
        r["image_url"] = f"/product-image/{code}/{color}" if color else f"/product-image/{code}/_"
    return rows


def agg_slow_moving(df: pd.DataFrame, group_cols, top_n=20):
    sub = df.copy()
    if sub.empty:
        return []
    agg = (
        sub.groupby(group_cols, as_index=False)
        .agg(销量=("数量", "sum"), 销售额=("销售额", "sum"), 选定价=("选定价", "max"))
        .sort_values(["销量", "销售额", "选定价"], ascending=[True, True, False])
        .head(int(top_n))
    )
    agg.insert(0, "排名", range(1, len(agg) + 1))
    rows = agg.to_dict(orient="records")
    for r in rows:
        r["销量"] = int(round(r.get("销量", 0)))
        r["销售额"] = round(float(r.get("销售额", 0)), 2)
        r["选定价"] = round(float(r.get("选定价", 0)), 2)
    return rows


def apply_inventory_filters(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    filtered = df.copy()
    if filtered.empty:
        return filtered
    if filters.get("category"):
        filtered = filtered[filtered["品类"].isin(filters["category"])]
    if filters.get("year_prefix"):
        filtered = filtered[filtered["年份代号"].isin(filters["year_prefix"])]
    if filters.get("season_code"):
        filtered = filtered[filtered["季节代号"].isin(filters["season_code"])]
    if filters.get("wave"):
        filtered = filtered[filtered["波段"].isin(filters["wave"])]
    return filtered


def build_slow_moving_rows(sales_df: pd.DataFrame, inventory_df: pd.DataFrame, cover_color_map: dict, top_n=20) -> list[dict]:
    if inventory_df.empty:
        return attach_image_urls(
            agg_slow_moving(sales_df, ["商品代码", "商品名称", "品类", "选定价"], top_n),
            cover_color_map,
        )

    inv = (
        inventory_df.groupby(["商品代码", "商品名称", "品类", "颜色代码", "颜色名称"], as_index=False)
        .agg(选定价=("选定价", "max"), 进货数量=("数量", "sum"))
    )
    sales = (
        sales_df.groupby(["商品代码", "颜色代码"], as_index=False)
        .agg(销量=("数量", "sum"), 销售额=("销售额", "sum"), 选定价=("选定价", "max"), 商品名称=("商品名称", "first"), 品类=("品类", "first"), 颜色名称=("颜色名称", "first"))
    ) if not sales_df.empty else pd.DataFrame(columns=["商品代码", "颜色代码", "销量", "销售额", "选定价", "商品名称", "品类", "颜色名称"])

    merged = inv.merge(sales, on=["商品代码", "颜色代码"], how="left", suffixes=("_inv", ""))
    merged["商品名称"] = merged["商品名称"].fillna(merged["商品名称_inv"]).fillna(merged["商品代码"])
    merged["品类"] = merged["品类"].fillna(merged["品类_inv"]).fillna("其他")
    merged["颜色名称"] = merged["颜色名称"].fillna(merged["颜色名称_inv"]).fillna("")
    merged["选定价"] = merged["选定价"].fillna(merged["选定价_inv"]).fillna(0)
    merged["销量"] = merged["销量"].fillna(0)
    merged["销售额"] = merged["销售额"].fillna(0)
    merged["进货数量"] = merged["进货数量"].fillna(0)
    merged = merged.sort_values(["销量", "销售额", "进货数量", "选定价"], ascending=[True, True, False, False]).head(int(top_n)).reset_index(drop=True)
    merged.insert(0, "排名", range(1, len(merged) + 1))
    rows = merged[["排名", "商品代码", "商品名称", "品类", "颜色代码", "颜色名称", "选定价", "销量", "销售额", "进货数量"]].to_dict(orient="records")
    for row in rows:
        row["销量"] = int(round(row.get("销量", 0)))
        row["销售额"] = round(float(row.get("销售额", 0)), 2)
        row["选定价"] = round(float(row.get("选定价", 0)), 2)
        row["进货数量"] = int(round(row.get("进货数量", 0)))
    return attach_image_urls(rows, cover_color_map)


def sales_summary(df):
    return {
        "总销量": int(df["数量"].sum()),
        "总销售额": round(float(df["销售额"].sum()), 2),
        "款色数": int(df[["商品代码", "颜色代码"]].drop_duplicates().shape[0]),
        "款号数": int(df["商品代码"].nunique()),
        "区域数": int(df["区域名称"].nunique()),
        "品类数": int(df["品类"].nunique()),
        "商店数": int(df["商店名称"].nunique()) if "商店名称" in df.columns else 0,
    }


def resolve_date_range(df: pd.DataFrame, request_args) -> tuple[pd.Timestamp | None, pd.Timestamp | None, str]:
    if df.empty or "日期" not in df.columns:
        return None, None, "week"

    min_date = df["日期"].min()
    max_date = df["日期"].max()
    preset = (request_args.get("date_preset") or "week").lower()
    start = pd.to_datetime(request_args.get("start_date"), errors="coerce")
    end = pd.to_datetime(request_args.get("end_date"), errors="coerce")

    if preset == "custom" and not pd.isna(start) and not pd.isna(end):
        return start.normalize(), end.normalize(), preset
    if preset == "month":
        start = (max_date - pd.Timedelta(days=29)).normalize()
    else:
        preset = "week"
        start = (max_date - pd.Timedelta(days=6)).normalize()
    return start, max_date.normalize(), preset


def request_multi_values(request_args, key: str) -> list[str]:
    values = request_args.getlist(key) if hasattr(request_args, "getlist") else []
    if not values:
        single = request_args.get(key)
        values = [single] if single else []
    normalized = []
    for value in values:
        text = str(value).strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def region_filter_values(region_values: list[str]) -> list[str] | None:
    selected = [value for value in region_values if value and value != "全国"]
    if not selected:
        return None
    expanded = []
    for value in selected:
        members = REGION_GROUPS.get(value)
        if members:
            expanded.extend(members)
        else:
            expanded.append(value)
    return list(dict.fromkeys(expanded))


def apply_filter_values(df: pd.DataFrame, filters: dict, include_region=True) -> pd.DataFrame:
    filtered = df.copy()
    start_date = pd.to_datetime(filters.get("start_date"), errors="coerce")
    end_date = pd.to_datetime(filters.get("end_date"), errors="coerce")
    if not pd.isna(start_date) and not pd.isna(end_date):
        filtered = filtered[(filtered["日期"] >= start_date.normalize()) & (filtered["日期"] <= end_date.normalize())]
    if filters.get("category"):
        filtered = filtered[filtered["品类"].isin(filters["category"])]
    if filters.get("store"):
        filtered = filtered[filtered["商店名称"].isin(filters["store"])]
    if filters.get("year_prefix"):
        filtered = filtered[filtered["年份代号"].isin(filters["year_prefix"])]
    if filters.get("season_code"):
        filtered = filtered[filtered["季节代号"].isin(filters["season_code"])]
    if filters.get("wave"):
        filtered = filtered[filtered["波段"].isin(filters["wave"])]
    if include_region:
        regions = region_filter_values(filters.get("region", []))
        if regions:
            filtered = filtered[filtered["区域名称"].isin(regions)]
    return filtered


def translate_filters_for_sql(filters: dict) -> dict:
    translated = {
        "start_date": filters.get("start_date", ""),
        "end_date": filters.get("end_date", ""),
        "source_file": filters.get("source_file", []),
        "wave": filters.get("wave", []),
    }
    if filters.get("region"):
        expanded_regions = region_filter_values(filters.get("region", []))
        if expanded_regions:
            translated["region_name"] = expanded_regions
    if filters.get("category"):
        translated["big_category_name"] = filters.get("category", [])
    if filters.get("store"):
        translated["store_name"] = filters.get("store", [])
    if filters.get("year_prefix"):
        translated["year"] = [str(YEAR_PREFIX_MAP.get(prefix, "")) for prefix in filters.get("year_prefix", []) if YEAR_PREFIX_MAP.get(prefix)]
    if filters.get("season_code"):
        translated["season_name"] = [SEASON_CODE_MAP.get(code, (None, ""))[1][:1] for code in filters.get("season_code", []) if SEASON_CODE_MAP.get(code)]
    return {key: value for key, value in translated.items() if value}


def apply_filters(df: pd.DataFrame, request_args) -> tuple[pd.DataFrame, dict]:
    category = request_multi_values(request_args, "category")
    region = request_multi_values(request_args, "region")
    store = request_multi_values(request_args, "store")
    year_prefix = request_multi_values(request_args, "year_prefix")
    season_code = request_multi_values(request_args, "season_code")
    wave = request_multi_values(request_args, "wave")
    start_date, end_date, date_preset = resolve_date_range(df, request_args)
    available_years = set(df["年份代号"].dropna().astype(str).tolist()) if "年份代号" in df.columns else set()
    if not year_prefix:
        default_year = DEFAULT_YEAR_PREFIX if DEFAULT_YEAR_PREFIX in available_years else next(iter(sorted(available_years)), "")
        year_prefix = [default_year] if default_year else []
    if not season_code:
        season_code = [DEFAULT_SEASON_CODE]
    if not region:
        region = ["全国"]

    filters = {
        "region": region,
        "category": category,
        "store": store,
        "year_prefix": year_prefix,
        "season_code": season_code,
        "wave": wave,
        "date_preset": date_preset,
        "start_date": start_date.strftime("%Y-%m-%d") if start_date is not None else "",
        "end_date": end_date.strftime("%Y-%m-%d") if end_date is not None else "",
    }
    return apply_filter_values(df, filters, include_region=True), filters


def build_cover_color_map(df: pd.DataFrame) -> dict:
    sub = df.copy()
    color_column = "颜色代码" if "颜色代码" in sub.columns else "color_code" if "color_code" in sub.columns else None
    if color_column is None:
        return {}
    quantity_column = "数量" if "数量" in sub.columns else "销量" if "销量" in sub.columns else None
    amount_column = "销售额" if "销售额" in sub.columns else "sales_amount" if "sales_amount" in sub.columns else None
    if quantity_column is None or amount_column is None:
        return {}
    sub = sub[sub[color_column].notna()]
    sub[color_column] = sub[color_column].astype(str).str.strip()
    sub = sub[sub[color_column].ne("") & sub[color_column].ne("nan")]
    if sub.empty:
        return {}

    cover = (
        sub.sort_values([quantity_column, amount_column], ascending=False)
        .groupby("商品代码", as_index=False)
        .first()[["商品代码", color_column]]
    )
    return dict(zip(cover["商品代码"], cover[color_column]))


def attach_image_urls(rows: list[dict], cover_color_map: dict) -> list[dict]:
    for r in rows:
        code = r.get("商品代码", "")
        color = r.get("颜色代码", "")
        if not color or color == "_":
            color = cover_color_map.get(code, "_")
        r["image_url"] = f"/product-image/{code}/{color}"
    return rows


def attach_image_urls_by_code(rows: list[dict], cover_color_map: dict) -> list[dict]:
    for r in rows:
        code = r.get("商品代码", "")
        color = cover_color_map.get(code, "_")
        r["image_url"] = f"/product-image/{code}/{color}"
    return rows


def ensure_dashboard_data() -> None:
    global DATA, INVENTORY_DATA
    if DATA is None or INVENTORY_DATA is None:
        try:
            reload_dashboard_data(trigger="lazy")
        except sqlite3.OperationalError:
            with get_db_connection() as conn:
                DATA = load_sales_from_db(conn)
            INVENTORY_DATA = refresh_inventory_data()


def get_latest_update_label() -> str:
    with get_db_connection() as conn:
        for sql in (
            "SELECT finished_at AS updated_at FROM import_log ORDER BY finished_at DESC LIMIT 1",
            "SELECT imported_at AS updated_at FROM imports ORDER BY imported_at DESC LIMIT 1",
        ):
            try:
                row = conn.execute(sql).fetchone()
            except sqlite3.OperationalError:
                continue
            if row and row["updated_at"]:
                updated_at = str(row["updated_at"])
                try:
                    parsed = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                    return parsed.strftime("%Y-%m-%d %H:%M")
                except ValueError:
                    return updated_at
    return ""


@app.route("/")
def index():
    return render_template(
        "index.html",
        page_title="经营驾驶舱",
        active_page="home",
        latest_update=get_latest_update_label() or "暂无更新时间",
        image_count=len(IMAGE_INDEX),
    )


@app.route("/api/dashboard")
def api_dashboard():
    top_n = int(request.args.get("top_n", APP_CONFIG["top_n"]))
    home_data = get_home_dashboard(request.args, top_n=top_n)
    sales_rows = home_data.pop("sales_rows", [])
    sales_df = pd.DataFrame(sales_rows).rename(columns={"销量": "数量"})
    inventory_df = INVENTORY_DATA if INVENTORY_DATA is not None else pd.DataFrame()
    filters = home_data.get("filters", {})
    inventory_filtered = apply_inventory_filters(inventory_df, filters)
    cover_color_map = build_cover_color_map(sales_df)
    slow_moving = build_slow_moving_rows(sales_df, inventory_filtered, cover_color_map, top_n)

    payload = {
        **home_data,
        "slow_moving": slow_moving,
        "filters": filters,
        "image_index_ready": IMAGE_INDEX_READY,
    }
    return jsonify(payload)


def make_matrix(df, top_n=30):
    base = agg_rank(df, ["商品代码", "商品名称", "品类", "选定价"], top_n)
    rows = []
    for item in base:
        code = item["商品代码"]
        row = {"商品代码": code, "商品名称": item["商品名称"], "品类": item["品类"], "全国排名": item["排名"], "全国销量": item["销量"]}
        for region, members in REGION_GROUPS.items():
            if region == "全国":
                continue
            reg_rank = agg_rank(df, ["商品代码", "商品名称", "品类", "选定价"], 9999, members)
            hit = next((x for x in reg_rank if x["商品代码"] == code), None)
            row[f"{region}排名"] = hit["排名"] if hit else "-"
            row[f"{region}销量"] = hit["销量"] if hit else 0
        rows.append(row)
    return rows


@app.route("/product-image/<code>/<color>")
def product_image(code, color):
    cache_key = normalize_key(code, color)
    path = IMAGE_INDEX.get(cache_key)
    if not path:
        path = resolve_image_path(APP_CONFIG["image_root"], code, color)
        if path:
            IMAGE_INDEX[cache_key] = path
    if not path or not os.path.exists(path):
        abort(404)
    return send_file(path)


@app.route("/api/reload")
def api_reload():
    try:
        result = reload_dashboard_data(trigger="manual")
        ok = (
            not result.get("daily_import", {}).get("lock_skipped", False)
            and int(result.get("daily_import", {}).get("failed", 0) or 0) == 0
            and bool(result.get("snapshot", {}).get("ok", True))
        )
        return jsonify({"ok": ok, **result})
    except Exception as exc:
        logger.exception("手动刷新失败：%s", exc)
        return jsonify({"ok": False, "error": str(exc)}), 500


def latest_excel(input_dir: str) -> str:
    return latest_matching_excel(input_dir, SALES_FILE_GLOB)


def parse_args():
    parser = argparse.ArgumentParser(description="BSERP零售 Product Explorer Flask Dashboard")
    parser.add_argument("--input", default=None, help="RPA导出的零售销售分析Excel路径")
    parser.add_argument("--input-dir", default=DEFAULT_INPUT_DIR, help="如果不传--input，则自动读取此文件夹最新xlsx")
    parser.add_argument("--image-root", default=DEFAULT_IMAGE_ROOT, help="商品图片根目录，默认 R:\\商品部")
    parser.add_argument("--host", default=DEFAULT_HOST, help="默认0.0.0.0，局域网其他电脑可访问")
    parser.add_argument("--port", default=DEFAULT_PORT, type=int, help="默认5000")
    parser.add_argument("--top-n", default=DEFAULT_TOP_N, type=int)
    return parser.parse_args()


if __name__ == "__main__":
    if len(sys.argv) == 1:
        APP_CONFIG.update({"excel_path": None, "inventory_path": None, "input_dir": DEFAULT_INPUT_DIR, "image_root": DEFAULT_IMAGE_ROOT, "top_n": DEFAULT_TOP_N})
        if _should_run_reloader_worker(reloader_enabled=True):
            try:
                initial_result = reload_dashboard_data(trigger="startup")
            except sqlite3.DatabaseError as exc:
                DATA = pd.DataFrame()
                INVENTORY_DATA = pd.DataFrame()
                initial_result = {"rows": 0, "images": 0, "image_index_ready": False, "loaded_at": time.strftime("%Y-%m-%d %H:%M:%S")}
                logger.warning("启动时数据加载被跳过：%s", exc)
        else:
            initial_result = {"rows": 0, "images": len(IMAGE_INDEX), "image_index_ready": IMAGE_INDEX_READY, "loaded_at": time.strftime("%Y-%m-%d %H:%M:%S")}
        start_auto_refresh_scheduler(reloader_enabled=True)
        logger.info("开发模式启动")
        logger.info("销售记录: %s 行；图片索引: %s 张；图片目录: %s", f"{initial_result['rows']:,}", f"{initial_result['images']:,}", DEFAULT_IMAGE_ROOT)
        logger.info("访问地址: http://127.0.0.1:5000")
        app.run(host="127.0.0.1", port=5000, debug=True, use_reloader=True)
    else:
        args = parse_args()
        excel_path = args.input or latest_excel(args.input_dir)
        APP_CONFIG.update({"excel_path": excel_path if args.input else None, "inventory_path": None, "input_dir": args.input_dir, "image_root": args.image_root, "top_n": args.top_n})
        try:
            initial_result = reload_dashboard_data(trigger="startup")
        except sqlite3.DatabaseError as exc:
            DATA = pd.DataFrame()
            INVENTORY_DATA = pd.DataFrame()
            initial_result = {"rows": 0, "images": 0, "image_index_ready": False, "loaded_at": time.strftime("%Y-%m-%d %H:%M:%S")}
            logger.warning("启动时数据加载被跳过：%s", exc)
        start_auto_refresh_scheduler(reloader_enabled=False)
        logger.info("已加载Excel: %s", excel_path)
        logger.info("销售记录: %s 行；图片索引: %s 张；图片目录: %s", f"{initial_result['rows']:,}", f"{initial_result['images']:,}", args.image_root)
        logger.info("访问地址: http://127.0.0.1:%s", args.port)
        logger.info("局域网访问: http://本机IP:%s", args.port)
        app.run(host=args.host, port=args.port, debug=False)
