import argparse
import json
import os
import re
import sqlite3
import time
from functools import lru_cache
from pathlib import Path
import threading

import pandas as pd
from flask import Flask, jsonify, render_template, request, send_file, abort

app = Flask(__name__)

DEFAULT_IMAGE_ROOT = r"R:\商品部"
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
REGION_GROUPS = {
    "全国": [],
    "北区": ["华北", "东北", "西北"],
    "中区": ["华中", "西南", "华东"],
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
SALES_FILE_GLOB = "零售销售分析*.xlsx"
INVENTORY_FILE_GLOB = "进货数据*.xlsx"

DATA = None
INVENTORY_DATA = None
IMAGE_INDEX = {}
IMAGE_INDEX_READY = False
IMAGE_INDEX_THREAD = None
IMAGE_INDEX_CACHE_PATH = Path(__file__).with_name("image_index.json")
DB_PATH = Path(__file__).with_name("retail_dashboard.db")
EXPORT_DATE_RE = re.compile(r"(20\d{2}-\d{2}-\d{2})")
APP_CONFIG = {
    "excel_path": None,
    "input_dir": "exports",
    "image_root": DEFAULT_IMAGE_ROOT,
    "top_n": 20,
}
DEFAULT_YEAR_PREFIX = "KU"
DEFAULT_SEASON_CODE = "2"


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


def enrich_season_columns(df: pd.DataFrame) -> pd.DataFrame:
    season_info = df["商品代码"].apply(infer_season)
    df["年份代号"] = season_info.apply(lambda item: item[0])
    df["年份"] = season_info.apply(lambda item: YEAR_PREFIX_MAP.get(item[0]))
    df["季节序"] = season_info.apply(lambda item: item[1])
    df["季节代号"] = season_info.apply(lambda item: item[2])
    df["季节"] = season_info.apply(lambda item: item[3])
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
            options.append({"value": prefix, "label": f"{prefix}({year})"})
    for prefix in df.get("年份代号", pd.Series(dtype=str)).dropna().unique().tolist():
        if prefix and prefix not in seen:
            year = YEAR_PREFIX_MAP.get(prefix)
            options.append({"value": prefix, "label": f"{prefix}({year})" if year else prefix})
    return options


def season_option_rows() -> list[dict]:
    return [
        {"value": code, "label": f"{code}({name})"}
        for code, (_, name) in sorted(SEASON_CODE_MAP.items(), key=lambda item: int(item[0]))
    ]


def load_sales(excel_path: str) -> pd.DataFrame:
    header_row = find_header_row(excel_path)
    df = pd.read_excel(excel_path, header=header_row)
    df.columns = [str(c).strip() for c in df.columns]
    keep = [c for c in ["商品代码", "商品名称", "颜色名称", "颜色代码", "选定价", "区域名称", "商店名称", "日期", "数量"] if c in df.columns]
    df = df[keep].copy()
    df = df[df["商品代码"].notna() & df["区域名称"].notna() & df["数量"].notna()]
    df["商品代码"] = df["商品代码"].astype(str).str.strip()
    df = df[df["商品代码"].apply(include_product_code)]
    df["颜色代码"] = df.get("颜色代码", "").astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
    df["颜色名称"] = df.get("颜色名称", "").fillna("").astype(str).str.strip()
    df["选定价"] = pd.to_numeric(df.get("选定价", 0), errors="coerce").fillna(0)
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
    keep = [c for c in ["商品代码", "颜色名称", "颜色代码", "选定价", "数量"] if c in df.columns]
    df = df[keep].copy()
    df = df[df["商品代码"].notna() & df["数量"].notna()]
    df["商品代码"] = df["商品代码"].astype(str).str.strip()
    df = df[df["商品代码"].apply(include_product_code)]
    df["颜色代码"] = df.get("颜色代码", "").astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
    df["颜色名称"] = df.get("颜色名称", "").fillna("").astype(str).str.strip()
    df["选定价"] = pd.to_numeric(df.get("选定价", 0), errors="coerce").fillna(0)
    df["数量"] = pd.to_numeric(df["数量"], errors="coerce").fillna(0)
    df["商品名称"] = df["商品代码"]
    df = enrich_season_columns(df)
    df["品类"] = df["商品代码"].apply(infer_category)
    return df


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


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


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
            import_sales_file(conn, APP_CONFIG["excel_path"])
        else:
            for excel_path in list_excel_files(APP_CONFIG["input_dir"], SALES_FILE_GLOB):
                import_sales_file(conn, excel_path)
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
        filtered = filtered[filtered["品类"].eq(filters["category"])]
    if filters.get("year_prefix"):
        filtered = filtered[filtered["年份代号"].eq(filters["year_prefix"])]
    if filters.get("season_code"):
        filtered = filtered[filtered["季节代号"].eq(filters["season_code"])]
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


def apply_filter_values(df: pd.DataFrame, filters: dict, include_region=True) -> pd.DataFrame:
    filtered = df.copy()
    start_date = pd.to_datetime(filters.get("start_date"), errors="coerce")
    end_date = pd.to_datetime(filters.get("end_date"), errors="coerce")
    if not pd.isna(start_date) and not pd.isna(end_date):
        filtered = filtered[(filtered["日期"] >= start_date.normalize()) & (filtered["日期"] <= end_date.normalize())]
    if filters.get("category"):
        filtered = filtered[filtered["品类"].eq(filters["category"])]
    if filters.get("store"):
        filtered = filtered[filtered["商店名称"].eq(filters["store"])]
    if filters.get("year_prefix"):
        filtered = filtered[filtered["年份代号"].eq(filters["year_prefix"])]
    if filters.get("season_code"):
        filtered = filtered[filtered["季节代号"].eq(filters["season_code"])]
    if include_region and filters.get("region") and filters["region"] != "全国":
        if filters["region"] in REGION_GROUPS:
            filtered = filtered[filtered["区域名称"].isin(REGION_GROUPS[filters["region"]])]
        else:
            filtered = filtered[filtered["区域名称"].eq(filters["region"])]
    return filtered


def apply_filters(df: pd.DataFrame, request_args) -> tuple[pd.DataFrame, dict]:
    category = request_args.get("category") or None
    region = request_args.get("region") or None
    store = request_args.get("store") or None
    year_prefix = request_args.get("year_prefix") or None
    season_code = request_args.get("season_code") or None
    start_date, end_date, date_preset = resolve_date_range(df, request_args)
    available_years = set(df["年份代号"].dropna().astype(str).tolist()) if "年份代号" in df.columns else set()
    if not year_prefix:
        year_prefix = DEFAULT_YEAR_PREFIX if DEFAULT_YEAR_PREFIX in available_years else next(iter(sorted(available_years)), "")
    if not season_code:
        season_code = DEFAULT_SEASON_CODE

    filters = {
        "region": region or "全国",
        "category": category or "",
        "store": store or "",
        "year_prefix": year_prefix or "",
        "season_code": season_code or "",
        "date_preset": date_preset,
        "start_date": start_date.strftime("%Y-%m-%d") if start_date is not None else "",
        "end_date": end_date.strftime("%Y-%m-%d") if end_date is not None else "",
    }
    return apply_filter_values(df, filters, include_region=True), filters


def build_cover_color_map(df: pd.DataFrame) -> dict:
    sub = df.copy()
    sub = sub[sub["颜色代码"].notna()]
    sub["颜色代码"] = sub["颜色代码"].astype(str).str.strip()
    sub = sub[sub["颜色代码"].ne("") & sub["颜色代码"].ne("nan")]
    if sub.empty:
        return {}

    cover = (
        sub.sort_values(["数量", "销售额"], ascending=False)
        .groupby("商品代码", as_index=False)
        .first()[["商品代码", "颜色代码"]]
    )
    return dict(zip(cover["商品代码"], cover["颜色代码"]))


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


@app.route("/")
def index():
    df = DATA
    summary = sales_summary(df)
    regions = sorted(df["区域名称"].dropna().unique().tolist())
    categories = sorted(df["品类"].dropna().unique().tolist())
    stores = sorted(df["商店名称"].dropna().unique().tolist()) if "商店名称" in df.columns else []
    year_options = year_option_rows(df)
    season_options = season_option_rows()
    date_min = df["日期"].min().strftime("%Y-%m-%d") if not df.empty and "日期" in df.columns else ""
    date_max = df["日期"].max().strftime("%Y-%m-%d") if not df.empty and "日期" in df.columns else ""
    return render_template(
        "index.html",
        summary=summary,
        regions=regions,
        categories=categories,
        stores=stores,
        year_options=year_options,
        season_options=season_options,
        default_year_prefix=DEFAULT_YEAR_PREFIX,
        default_season_code=DEFAULT_SEASON_CODE,
        date_min=date_min,
        date_max=date_max,
        image_count=len(IMAGE_INDEX),
    )


@app.route("/api/dashboard")
def api_dashboard():
    df = DATA
    inventory_df = INVENTORY_DATA if INVENTORY_DATA is not None else pd.DataFrame()
    top_n = int(request.args.get("top_n", APP_CONFIG["top_n"]))
    filtered, filters = apply_filters(df, request.args)
    region_scope = apply_filter_values(df, filters, include_region=False)
    inventory_filtered = apply_inventory_filters(inventory_df, filters)
    cover_color_map = build_cover_color_map(df)

    region_top = {}
    for name, members in REGION_GROUPS.items():
        region_top[name] = agg_rank(region_scope, ["商品代码", "商品名称", "品类", "选定价"], top_n, members or None, filters["category"] or None)

    slow_moving = build_slow_moving_rows(filtered, inventory_filtered, cover_color_map, top_n)

    by_region = (
        filtered.groupby("区域名称", as_index=False).agg(销量=("数量", "sum"), 销售额=("销售额", "sum"))
        .sort_values("销量", ascending=False).to_dict(orient="records")
    )
    by_category = (
        filtered.groupby("品类", as_index=False).agg(销量=("数量", "sum"), 销售额=("销售额", "sum"))
        .sort_values("销量", ascending=False).to_dict(orient="records")
    )
    by_store = (
        filtered.groupby("商店名称", as_index=False).agg(销量=("数量", "sum"), 销售额=("销售额", "sum"))
        .sort_values(["销量", "销售额"], ascending=False)
        .head(top_n)
        .to_dict(orient="records")
    )
    for arr in (by_region, by_category, by_store):
        for r in arr:
            r["销量"] = int(round(r["销量"]))
            r["销售额"] = round(float(r["销售额"]), 2)

    region_top = {
        name: attach_image_urls_by_code(rows, cover_color_map)
        for name, rows in region_top.items()
    }
    matrix = attach_image_urls_by_code(make_matrix(filtered, top_n=30), cover_color_map)
    return jsonify({
        "summary": sales_summary(filtered),
        "global_top": attach_image_urls(agg_rank(filtered, ["商品代码", "商品名称", "品类", "选定价"], top_n), cover_color_map),
        "color_top": agg_rank(filtered, ["商品代码", "颜色代码", "颜色名称", "商品名称", "品类", "选定价"], top_n),
        "slow_moving": slow_moving,
        "region_top": region_top,
        "by_region": by_region,
        "by_category": by_category,
        "by_store": by_store,
        "matrix": matrix,
        "filters": filters,
        "meta": {
            "date_min": df["日期"].min().strftime("%Y-%m-%d") if not df.empty else "",
            "date_max": df["日期"].max().strftime("%Y-%m-%d") if not df.empty else "",
            "default_year_prefix": DEFAULT_YEAR_PREFIX,
            "default_season_code": DEFAULT_SEASON_CODE,
            "year_options": year_option_rows(df),
            "season_options": season_option_rows(),
        },
        "image_index_ready": IMAGE_INDEX_READY,
    })


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
    global DATA, INVENTORY_DATA
    DATA = refresh_sales_data()
    INVENTORY_DATA = refresh_inventory_data()
    start_image_index_build(APP_CONFIG["image_root"])
    resolve_image_path.cache_clear()
    return jsonify({"ok": True, "rows": len(DATA), "images": len(IMAGE_INDEX), "image_index_ready": IMAGE_INDEX_READY, "loaded_at": time.strftime("%Y-%m-%d %H:%M:%S")})


def latest_excel(input_dir: str) -> str:
    return latest_matching_excel(input_dir, SALES_FILE_GLOB)


def parse_args():
    parser = argparse.ArgumentParser(description="BSERP零售Top20 Flask Dashboard")
    parser.add_argument("--input", default=None, help="RPA导出的零售销售分析Excel路径")
    parser.add_argument("--input-dir", default="exports", help="如果不传--input，则自动读取此文件夹最新xlsx")
    parser.add_argument("--image-root", default=DEFAULT_IMAGE_ROOT, help="商品图片根目录，默认 R:\\商品部")
    parser.add_argument("--host", default="0.0.0.0", help="默认0.0.0.0，局域网其他电脑可访问")
    parser.add_argument("--port", default=5000, type=int, help="默认5000")
    parser.add_argument("--top-n", default=20, type=int)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    excel_path = args.input or latest_excel(args.input_dir)
    APP_CONFIG.update({"excel_path": excel_path if args.input else None, "inventory_path": None, "input_dir": args.input_dir, "image_root": args.image_root, "top_n": args.top_n})
    DATA = refresh_sales_data()
    INVENTORY_DATA = refresh_inventory_data()
    start_image_index_build(args.image_root)
    print(f"已加载Excel: {excel_path}")
    print(f"销售记录: {len(DATA):,} 行；图片索引: {len(IMAGE_INDEX):,} 张；图片目录: {args.image_root}")
    print(f"访问地址: http://127.0.0.1:{args.port}")
    print(f"局域网访问: http://本机IP:{args.port}")
    app.run(host=args.host, port=args.port, debug=False)
