import argparse
import json
import os
import re
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
    "T": "T恤/上衣",
    "K": "裤装",
    "N": "牛仔",
    "V": "针织/外套",
    "W": "外套",
    "A": "配饰/吊带",
    "B": "包/配饰",
    "P": "配饰/其他",
    "S": "裙装/套装",
    "C": "中袖/衬衫",
}

DATA = None
IMAGE_INDEX = {}
IMAGE_INDEX_READY = False
IMAGE_INDEX_THREAD = None
IMAGE_INDEX_CACHE_PATH = Path(__file__).with_name("image_index.json")
APP_CONFIG = {
    "excel_path": None,
    "image_root": DEFAULT_IMAGE_ROOT,
    "top_n": 20,
}


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


def load_sales(excel_path: str) -> pd.DataFrame:
    header_row = find_header_row(excel_path)
    df = pd.read_excel(excel_path, header=header_row)
    df.columns = [str(c).strip() for c in df.columns]
    keep = [c for c in ["商品代码", "商品名称", "颜色名称", "颜色代码", "选定价", "区域名称", "数量"] if c in df.columns]
    df = df[keep].copy()
    df = df[df["商品代码"].notna() & df["区域名称"].notna() & df["数量"].notna()]
    df["商品代码"] = df["商品代码"].astype(str).str.strip()
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
    df["品类"] = df["商品代码"].apply(infer_category)
    df["销售额"] = df["数量"] * df["选定价"]
    return df


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


def sales_summary(df):
    return {
        "总销量": int(df["数量"].sum()),
        "总销售额": round(float(df["销售额"].sum()), 2),
        "款色数": int(df[["商品代码", "颜色代码"]].drop_duplicates().shape[0]),
        "款号数": int(df["商品代码"].nunique()),
        "区域数": int(df["区域名称"].nunique()),
        "品类数": int(df["品类"].nunique()),
    }


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


@app.route("/")
def index():
    df = DATA
    summary = sales_summary(df)
    regions = sorted(df["区域名称"].dropna().unique().tolist())
    categories = sorted(df["品类"].dropna().unique().tolist())
    return render_template("index.html", summary=summary, regions=regions, categories=categories, image_count=len(IMAGE_INDEX))


@app.route("/api/dashboard")
def api_dashboard():
    df = DATA
    top_n = int(request.args.get("top_n", APP_CONFIG["top_n"]))
    category = request.args.get("category") or None
    region = request.args.get("region") or None
    filtered = df.copy()
    if category:
        filtered = filtered[filtered["品类"].eq(category)]
    if region and region != "全国":
        if region in REGION_GROUPS:
            filtered = filtered[filtered["区域名称"].isin(REGION_GROUPS[region])]
        else:
            filtered = filtered[filtered["区域名称"].eq(region)]

    region_top = {}
    for name, members in REGION_GROUPS.items():
        region_top[name] = agg_rank(df, ["商品代码", "商品名称", "品类", "选定价"], top_n, members or None, category)

    category_top = {}
    for cat in sorted(df["品类"].unique()):
        category_top[cat] = agg_rank(df, ["商品代码", "商品名称", "品类", "选定价"], top_n, None, cat)

    by_region = (
        filtered.groupby("区域名称", as_index=False).agg(销量=("数量", "sum"), 销售额=("销售额", "sum"))
        .sort_values("销量", ascending=False).to_dict(orient="records")
    )
    by_category = (
        filtered.groupby("品类", as_index=False).agg(销量=("数量", "sum"), 销售额=("销售额", "sum"))
        .sort_values("销量", ascending=False).to_dict(orient="records")
    )
    for arr in (by_region, by_category):
        for r in arr:
            r["销量"] = int(round(r["销量"]))
            r["销售额"] = round(float(r["销售额"]), 2)

    cover_color_map = build_cover_color_map(filtered)
    matrix = make_matrix(df, top_n=30)
    return jsonify({
        "summary": sales_summary(filtered),
        "global_top": attach_image_urls(agg_rank(filtered, ["商品代码", "商品名称", "品类", "选定价"], top_n), cover_color_map),
        "color_top": agg_rank(filtered, ["商品代码", "颜色代码", "颜色名称", "商品名称", "品类", "选定价"], top_n),
        "region_top": region_top,
        "category_top": category_top,
        "by_region": by_region,
        "by_category": by_category,
        "matrix": matrix,
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
    global DATA
    DATA = load_sales(APP_CONFIG["excel_path"])
    start_image_index_build(APP_CONFIG["image_root"])
    resolve_image_path.cache_clear()
    return jsonify({"ok": True, "rows": len(DATA), "images": len(IMAGE_INDEX), "image_index_ready": IMAGE_INDEX_READY, "loaded_at": time.strftime("%Y-%m-%d %H:%M:%S")})


def latest_excel(input_dir: str) -> str:
    folder = Path(input_dir)
    files = sorted(
        [p for p in folder.glob("*.xlsx") if not p.name.startswith("~$")],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not files:
        raise FileNotFoundError(f"目录中没有找到xlsx文件: {input_dir}")
    return str(files[0])


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
    APP_CONFIG.update({"excel_path": excel_path, "image_root": args.image_root, "top_n": args.top_n})
    DATA = load_sales(excel_path)
    start_image_index_build(args.image_root)
    print(f"已加载Excel: {excel_path}")
    print(f"销售记录: {len(DATA):,} 行；图片索引: {len(IMAGE_INDEX):,} 张；图片目录: {args.image_root}")
    print(f"访问地址: http://127.0.0.1:{args.port}")
    print(f"局域网访问: http://本机IP:{args.port}")
    app.run(host=args.host, port=args.port, debug=False)
