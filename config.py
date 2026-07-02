from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_IMAGE_ROOT = r"R:\商品部"
DEFAULT_INPUT_DIR = "exports"
DEFAULT_TOP_N = 20
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 5000
DEFAULT_YEAR_PREFIX = "KU"
DEFAULT_SEASON_CODE = "2"
AUTO_REFRESH_HOUR = 7
AUTO_REFRESH_MINUTE = 10
SALES_FILE_GLOB = "零售销售分析*.xlsx"
SALES_CSV_GLOB = "零售销售分析*.csv"
INVENTORY_FILE_GLOB = "进货数据*.xlsx"
IMAGE_INDEX_CACHE_PATH = BASE_DIR / "image_index.json"
DB_PATH = BASE_DIR / "retail_dashboard.db"


def build_app_config() -> dict:
    return {
        "excel_path": None,
        "input_dir": DEFAULT_INPUT_DIR,
        "image_root": DEFAULT_IMAGE_ROOT,
        "top_n": DEFAULT_TOP_N,
    }
