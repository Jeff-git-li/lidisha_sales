from __future__ import annotations

from typing import Any

from assets.asset_service import get_product_image
from database import get_db_connection
from queries.retail_queries import JOINED_CTE, _query_all, _query_one


SNAPSHOT_LIMIT = 2
REGION_MAP = {
    "全国": [],
    "北区": ["华北", "东北", "西北"],
    "中区": ["华中", "西南", "华东", "河南"],
    "南区": ["华南"],
}


def _ensure_tables(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS dashboard_snapshot (
            snapshot_date TEXT PRIMARY KEY,
            total_qty INTEGER NOT NULL DEFAULT 0,
            total_amount REAL NOT NULL DEFAULT 0,
            core_product_count INTEGER NOT NULL DEFAULT 0,
            store_count INTEGER NOT NULL DEFAULT 0,
            avg_daily_sales REAL NOT NULL DEFAULT 0,
            average_discount_rate REAL NOT NULL DEFAULT 0,
            latest_data_date TEXT NOT NULL DEFAULT '',
            summary_text TEXT NOT NULL DEFAULT '',
            action_text TEXT NOT NULL DEFAULT '',
            bullet_1 TEXT NOT NULL DEFAULT '',
            bullet_2 TEXT NOT NULL DEFAULT '',
            bullet_3 TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS dashboard_regions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date TEXT NOT NULL,
            rank INTEGER NOT NULL,
            region_name TEXT NOT NULL,
            total_qty INTEGER NOT NULL DEFAULT 0,
            total_amount REAL NOT NULL DEFAULT 0,
            product_count INTEGER NOT NULL DEFAULT 0,
            store_count INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS dashboard_top_products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date TEXT NOT NULL,
            rank INTEGER NOT NULL,
            product_code TEXT NOT NULL,
            color_code TEXT NOT NULL,
            product_name TEXT NOT NULL,
            color_name TEXT NOT NULL,
            category_name TEXT NOT NULL,
            big_category_name TEXT NOT NULL,
            year TEXT NOT NULL,
            season_name TEXT NOT NULL,
            wave TEXT NOT NULL,
            designer_name TEXT NOT NULL,
            standard_price REAL NOT NULL DEFAULT 0,
            sales_qty INTEGER NOT NULL DEFAULT 0,
            sales_amount REAL NOT NULL DEFAULT 0,
            store_coverage INTEGER NOT NULL DEFAULT 0,
            sales_rows INTEGER NOT NULL DEFAULT 0,
            image_url TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS dashboard_color_top_products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date TEXT NOT NULL,
            rank INTEGER NOT NULL,
            product_code TEXT NOT NULL,
            color_code TEXT NOT NULL,
            product_name TEXT NOT NULL,
            color_name TEXT NOT NULL,
            category_name TEXT NOT NULL,
            big_category_name TEXT NOT NULL,
            year TEXT NOT NULL,
            season_name TEXT NOT NULL,
            wave TEXT NOT NULL,
            designer_name TEXT NOT NULL,
            standard_price REAL NOT NULL DEFAULT 0,
            sales_qty INTEGER NOT NULL DEFAULT 0,
            sales_amount REAL NOT NULL DEFAULT 0,
            sales_rows INTEGER NOT NULL DEFAULT 0,
            image_url TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS dashboard_category_summary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date TEXT NOT NULL,
            rank INTEGER NOT NULL,
            category_name TEXT NOT NULL,
            total_qty INTEGER NOT NULL DEFAULT 0,
            total_amount REAL NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS dashboard_store_summary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date TEXT NOT NULL,
            rank INTEGER NOT NULL,
            store_name TEXT NOT NULL,
            total_qty INTEGER NOT NULL DEFAULT 0,
            total_amount REAL NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS dashboard_daily_sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date TEXT NOT NULL,
            sale_date TEXT NOT NULL,
            total_qty INTEGER NOT NULL DEFAULT 0,
            total_amount REAL NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS dashboard_region_top_products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date TEXT NOT NULL,
            region_name TEXT NOT NULL,
            rank INTEGER NOT NULL,
            product_code TEXT NOT NULL,
            color_code TEXT NOT NULL,
            product_name TEXT NOT NULL,
            sales_qty INTEGER NOT NULL DEFAULT 0,
            sales_amount REAL NOT NULL DEFAULT 0,
            image_url TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS dashboard_matrix (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date TEXT NOT NULL,
            rank INTEGER NOT NULL,
            product_code TEXT NOT NULL,
            product_name TEXT NOT NULL,
            category_name TEXT NOT NULL,
            image_url TEXT NOT NULL DEFAULT '',
            national_rank INTEGER NOT NULL DEFAULT 0,
            national_qty INTEGER NOT NULL DEFAULT 0,
            north_rank INTEGER,
            north_qty INTEGER NOT NULL DEFAULT 0,
            central_rank INTEGER,
            central_qty INTEGER NOT NULL DEFAULT 0,
            south_rank INTEGER,
            south_qty INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS dashboard_sales_rows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date TEXT NOT NULL,
            product_code TEXT NOT NULL,
            color_code TEXT NOT NULL,
            product_name TEXT NOT NULL,
            color_name TEXT NOT NULL,
            category_name TEXT NOT NULL,
            big_category_name TEXT NOT NULL,
            year TEXT NOT NULL,
            season_name TEXT NOT NULL,
            wave TEXT NOT NULL,
            designer_name TEXT NOT NULL,
            standard_price REAL NOT NULL DEFAULT 0,
            sales_qty INTEGER NOT NULL DEFAULT 0,
            sales_amount REAL NOT NULL DEFAULT 0,
            sales_rows INTEGER NOT NULL DEFAULT 0,
            image_url TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS dashboard_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date TEXT NOT NULL,
            alert_order INTEGER NOT NULL,
            alert_type TEXT NOT NULL,
            alert_title TEXT NOT NULL,
            alert_state TEXT NOT NULL,
            alert_text TEXT NOT NULL DEFAULT ''
        )
        """
    )

    columns = {row[1] for row in conn.execute("PRAGMA table_info(dashboard_snapshot)").fetchall()}
    if "average_discount_rate" not in columns:
        conn.execute("ALTER TABLE dashboard_snapshot ADD COLUMN average_discount_rate REAL NOT NULL DEFAULT 0")


def _snapshot_dates(limit: int = SNAPSHOT_LIMIT) -> list[str]:
    rows = _query_all(
        f"""
        {JOINED_CTE}
        SELECT DISTINCT sale_date
        FROM joined
        WHERE COALESCE(NULLIF(TRIM(year), ''), '') <> '' AND COALESCE(NULLIF(TRIM(season_name), ''), '') <> ''
        ORDER BY sale_date DESC
        LIMIT ?
        """,
        [int(limit)],
    )
    return [str(row.get("sale_date", "") or "") for row in rows if row.get("sale_date")]


def _build_day(conn, sale_date: str) -> None:
    summary_row = _query_one(
        f"""
        {JOINED_CTE}
        SELECT
            COALESCE(SUM(qty), 0) AS total_qty,
            COALESCE(SUM(effective_amount), 0) AS total_amount,
            COALESCE(SUM(standard_amount), 0) AS total_standard_amount,
            CASE
                WHEN COALESCE(SUM(standard_amount), 0) > 0 THEN SUM(amount) * 1.0 / SUM(standard_amount)
                ELSE NULL
            END AS average_discount_rate,
            COUNT(DISTINCT product_code) AS core_product_count,
            COUNT(DISTINCT store_code) AS store_count,
            CASE WHEN COUNT(DISTINCT sale_date) = 0 THEN 0 ELSE ROUND(COALESCE(SUM(qty), 0) * 1.0 / COUNT(DISTINCT sale_date), 2) END AS avg_daily_sales,
            COALESCE(MAX(sale_date), '') AS latest_data_date
        FROM joined
        WHERE sale_date = ?
          AND COALESCE(NULLIF(TRIM(year), ''), '') <> ''
          AND COALESCE(NULLIF(TRIM(season_name), ''), '') <> ''
        """,
        [sale_date],
    )
    conn.execute(
        """
        INSERT INTO dashboard_snapshot (
            snapshot_date, total_qty, total_amount, core_product_count, store_count, avg_daily_sales,
            average_discount_rate, latest_data_date, summary_text, action_text, bullet_1, bullet_2, bullet_3
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            sale_date,
            int(summary_row.get("total_qty", 0) or 0),
            float(summary_row.get("total_amount", 0) or 0),
            int(summary_row.get("core_product_count", 0) or 0),
            int(summary_row.get("store_count", 0) or 0),
            float(summary_row.get("avg_daily_sales", 0) or 0),
            summary_row.get("average_discount_rate"),
            str(summary_row.get("latest_data_date", "") or sale_date),
            f"最新销售日销售{float(summary_row.get('total_amount', 0) or 0):.2f}，重点关注爆款和区域变化。",
            "建议优先补货最新销售日 Top 5 商品，并持续跟踪重点区域。",
            "销售件数和门店数维持可读摘要。",
            "Top 5 商品已固化为快照。",
            "区域摘要覆盖前四个区域。",
        ),
    )

    top_products = _query_all(
        f"""
        {JOINED_CTE}
        SELECT
            product_code,
            color_code,
            MAX(product_name) AS product_name,
            MAX(color_name) AS color_name,
            MAX(category_name) AS category_name,
            MAX(big_category_name) AS big_category_name,
            MAX(year) AS year,
            MAX(season_name) AS season_name,
            MAX(wave) AS wave,
            MAX(designer_name) AS designer_name,
            MAX(standard_price) AS standard_price,
            COALESCE(SUM(qty), 0) AS sales_qty,
            COALESCE(SUM(effective_amount), 0) AS sales_amount,
            COUNT(DISTINCT store_code) AS store_coverage,
            COUNT(*) AS sales_rows
        FROM joined
        WHERE sale_date = ?
          AND COALESCE(NULLIF(TRIM(year), ''), '') <> ''
          AND COALESCE(NULLIF(TRIM(season_name), ''), '') <> ''
        GROUP BY product_code, color_code
        ORDER BY sales_amount DESC, sales_qty DESC, product_code ASC, color_code ASC
        LIMIT 5
        """,
        [sale_date],
    )

    color_top = _query_all(
        f"""
        {JOINED_CTE}
        SELECT
            product_code,
            color_code,
            MAX(product_name) AS product_name,
            MAX(color_name) AS color_name,
            MAX(category_name) AS category_name,
            MAX(big_category_name) AS big_category_name,
            MAX(year) AS year,
            MAX(season_name) AS season_name,
            MAX(wave) AS wave,
            MAX(designer_name) AS designer_name,
            MAX(standard_price) AS standard_price,
            COALESCE(SUM(qty), 0) AS sales_qty,
            COALESCE(SUM(effective_amount), 0) AS sales_amount,
            COUNT(*) AS sales_rows
        FROM joined
        WHERE sale_date = ?
          AND COALESCE(NULLIF(TRIM(year), ''), '') <> ''
          AND COALESCE(NULLIF(TRIM(season_name), ''), '') <> ''
        GROUP BY product_code, color_code
        ORDER BY sales_amount DESC, sales_qty DESC, product_code ASC, color_code ASC
        LIMIT 5
        """,
        [sale_date],
    )

    region_rows = _query_all(
        f"""
        {JOINED_CTE}
        SELECT
            COALESCE(region_name, '未分区') AS region_name,
            COALESCE(SUM(qty), 0) AS total_qty,
            COALESCE(SUM(effective_amount), 0) AS total_amount,
            COUNT(DISTINCT product_code) AS product_count,
            COUNT(DISTINCT store_code) AS store_count
        FROM joined
        WHERE sale_date = ?
          AND COALESCE(NULLIF(TRIM(year), ''), '') <> ''
          AND COALESCE(NULLIF(TRIM(season_name), ''), '') <> ''
        GROUP BY COALESCE(region_name, '未分区')
        ORDER BY total_amount DESC, total_qty DESC, region_name ASC
        LIMIT 4
        """,
        [sale_date],
    )

    daily_sales = _query_all(
        f"""
        {JOINED_CTE}
        SELECT sale_date, COALESCE(SUM(qty), 0) AS total_qty, COALESCE(SUM(effective_amount), 0) AS total_amount
        FROM joined
        WHERE sale_date = ?
          AND COALESCE(NULLIF(TRIM(year), ''), '') <> ''
          AND COALESCE(NULLIF(TRIM(season_name), ''), '') <> ''
        GROUP BY sale_date
        """,
        [sale_date],
    )

    category_rows = _query_all(
        f"""
        {JOINED_CTE}
        SELECT COALESCE(category_name, '未分类') AS category_name, COALESCE(SUM(qty), 0) AS total_qty, COALESCE(SUM(effective_amount), 0) AS total_amount
        FROM joined
        WHERE sale_date = ?
          AND COALESCE(NULLIF(TRIM(year), ''), '') <> ''
          AND COALESCE(NULLIF(TRIM(season_name), ''), '') <> ''
        GROUP BY COALESCE(category_name, '未分类')
        ORDER BY total_amount DESC, total_qty DESC, category_name ASC
        """,
        [sale_date],
    )

    store_rows = _query_all(
        f"""
        {JOINED_CTE}
        SELECT COALESCE(store_name, store_code) AS store_name, COALESCE(SUM(qty), 0) AS total_qty, COALESCE(SUM(effective_amount), 0) AS total_amount
        FROM joined
        WHERE sale_date = ?
          AND COALESCE(NULLIF(TRIM(year), ''), '') <> ''
          AND COALESCE(NULLIF(TRIM(season_name), ''), '') <> ''
        GROUP BY COALESCE(store_name, store_code)
        ORDER BY total_qty DESC, total_amount DESC, store_name ASC
        LIMIT 20
        """,
        [sale_date],
    )

    matrix_rows = _query_all(
        f"""
        {JOINED_CTE}, product_base AS (
            SELECT
                product_code,
                MAX(product_name) AS product_name,
                MAX(category_name) AS category_name,
                COALESCE(SUM(qty), 0) AS national_qty,
                ROW_NUMBER() OVER (ORDER BY COALESCE(SUM(qty), 0) DESC, COALESCE(SUM(effective_amount), 0) DESC, product_code ASC) AS national_rank
            FROM joined
            WHERE sale_date = ?
              AND COALESCE(NULLIF(TRIM(year), ''), '') <> ''
              AND COALESCE(NULLIF(TRIM(season_name), ''), '') <> ''
            GROUP BY product_code
            LIMIT 30
        )
        SELECT national_rank AS rank, product_code, product_name, category_name, '' AS image_url,
               national_rank, national_qty,
               NULL AS north_rank, 0 AS north_qty,
               NULL AS central_rank, 0 AS central_qty,
               NULL AS south_rank, 0 AS south_qty
        FROM product_base
        ORDER BY national_rank ASC
        """,
        [sale_date],
    )

    region_top_rows: dict[str, list[dict[str, Any]]] = {"全国": [dict(row) for row in top_products]}
    for region_name, members in REGION_MAP.items():
        if region_name == "全国" or not members:
            continue
        placeholders = ", ".join(["?"] * len(members))
        region_top_rows[region_name] = _query_all(
            f"""
            {JOINED_CTE}
            SELECT
                product_code,
                color_code,
                MAX(product_name) AS product_name,
                COALESCE(SUM(qty), 0) AS sales_qty,
                COALESCE(SUM(effective_amount), 0) AS sales_amount
            FROM joined
            WHERE sale_date = ?
              AND COALESCE(NULLIF(TRIM(year), ''), '') <> ''
              AND COALESCE(NULLIF(TRIM(season_name), ''), '') <> ''
              AND COALESCE(NULLIF(TRIM(region_name), ''), '') IN ({placeholders})
            GROUP BY product_code, color_code
            ORDER BY sales_amount DESC, sales_qty DESC, product_code ASC, color_code ASC
            LIMIT 20
            """,
            [sale_date, *members],
        )

    sales_rows = _query_all(
        f"""
        {JOINED_CTE}
        SELECT
            product_code,
            color_code,
            MAX(product_name) AS product_name,
            MAX(color_name) AS color_name,
            MAX(category_name) AS category_name,
            MAX(big_category_name) AS big_category_name,
            MAX(year) AS year,
            MAX(season_name) AS season_name,
            MAX(wave) AS wave,
            MAX(designer_name) AS designer_name,
            MAX(standard_price) AS standard_price,
            COALESCE(SUM(qty), 0) AS sales_qty,
            COALESCE(SUM(effective_amount), 0) AS sales_amount,
            COUNT(*) AS sales_rows
        FROM joined
        WHERE sale_date = ?
          AND COALESCE(NULLIF(TRIM(year), ''), '') <> ''
          AND COALESCE(NULLIF(TRIM(season_name), ''), '') <> ''
        GROUP BY product_code, color_code
        ORDER BY sales_amount DESC, sales_qty DESC, product_code ASC, color_code ASC
        """,
        [sale_date],
    )

    alerts = [
        (1, "inventory", "库存提醒", "建设中", "待补充库存联动规则"),
        (2, "slow_moving", "滞销商品", "建设中", "待补充滞销识别规则"),
        (3, "size_gap", "尺码断层风险", "建设中", "待补充尺码风险规则"),
    ]

    for table in (
        "dashboard_snapshot",
        "dashboard_regions",
        "dashboard_top_products",
        "dashboard_color_top_products",
        "dashboard_category_summary",
        "dashboard_store_summary",
        "dashboard_daily_sales",
        "dashboard_region_top_products",
        "dashboard_matrix",
        "dashboard_sales_rows",
        "dashboard_alerts",
    ):
        conn.execute(f"DELETE FROM {table} WHERE snapshot_date = ?", (sale_date,))

    conn.execute(
        """
        INSERT INTO dashboard_snapshot (
            snapshot_date, total_qty, total_amount, core_product_count, store_count, avg_daily_sales,
            average_discount_rate, latest_data_date, summary_text, action_text, bullet_1, bullet_2, bullet_3
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            sale_date,
            int(summary_row.get("total_qty", 0) or 0),
            float(summary_row.get("total_amount", 0) or 0),
            int(summary_row.get("core_product_count", 0) or 0),
            int(summary_row.get("store_count", 0) or 0),
            float(summary_row.get("avg_daily_sales", 0) or 0),
            summary_row.get("average_discount_rate"),
            str(summary_row.get("latest_data_date", "") or sale_date),
            f"最新销售日销售{float(summary_row.get('total_amount', 0) or 0):.2f}，重点关注爆款和区域变化。",
            "建议优先补货最新销售日 Top 5 商品，并持续跟踪重点区域。",
            "销售件数和门店数维持可读摘要。",
            "Top 5 商品已固化为快照。",
            "区域摘要覆盖前四个区域。",
        ),
    )

    for index, row in enumerate(region_rows, start=1):
        conn.execute(
            """
            INSERT INTO dashboard_regions (
                snapshot_date, rank, region_name, total_qty, total_amount, product_count, store_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sale_date,
                index,
                str(row.get("region_name", "未分区") or "未分区"),
                int(row.get("total_qty", 0) or 0),
                float(row.get("total_amount", 0) or 0),
                int(row.get("product_count", 0) or 0),
                int(row.get("store_count", 0) or 0),
            ),
        )

    for index, row in enumerate(top_products, start=1):
        code = str(row.get("product_code", "") or "")
        color = str(row.get("color_code", "") or "_")
        conn.execute(
            """
            INSERT INTO dashboard_top_products (
                snapshot_date, rank, product_code, color_code, product_name, color_name, category_name,
                big_category_name, year, season_name, wave, designer_name, standard_price, sales_qty,
                sales_amount, store_coverage, sales_rows, image_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sale_date,
                index,
                code,
                color,
                str(row.get("product_name", "") or ""),
                str(row.get("color_name", "") or ""),
                str(row.get("category_name", "") or ""),
                str(row.get("big_category_name", "") or ""),
                str(row.get("year", "") or ""),
                str(row.get("season_name", "") or ""),
                str(row.get("wave", "") or ""),
                str(row.get("designer_name", "") or ""),
                float(row.get("standard_price", 0) or 0),
                int(row.get("sales_qty", 0) or 0),
                float(row.get("sales_amount", 0) or 0),
                int(row.get("store_coverage", 0) or 0),
                int(row.get("sales_rows", 0) or 0),
                get_product_image(code, color).get("image_url", ""),
            ),
        )

    for index, row in enumerate(color_top, start=1):
        code = str(row.get("product_code", "") or "")
        color = str(row.get("color_code", "") or "_")
        conn.execute(
            """
            INSERT INTO dashboard_color_top_products (
                snapshot_date, rank, product_code, color_code, product_name, color_name, category_name,
                big_category_name, year, season_name, wave, designer_name, standard_price, sales_qty,
                sales_amount, sales_rows, image_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sale_date,
                index,
                code,
                color,
                str(row.get("product_name", "") or ""),
                str(row.get("color_name", "") or ""),
                str(row.get("category_name", "") or ""),
                str(row.get("big_category_name", "") or ""),
                str(row.get("year", "") or ""),
                str(row.get("season_name", "") or ""),
                str(row.get("wave", "") or ""),
                str(row.get("designer_name", "") or ""),
                float(row.get("standard_price", 0) or 0),
                int(row.get("sales_qty", 0) or 0),
                float(row.get("sales_amount", 0) or 0),
                int(row.get("sales_rows", 0) or 0),
                get_product_image(code, color).get("image_url", ""),
            ),
        )

    for index, row in enumerate(daily_sales, start=1):
        conn.execute(
            """
            INSERT INTO dashboard_daily_sales (
                snapshot_date, sale_date, total_qty, total_amount
            ) VALUES (?, ?, ?, ?)
            """,
            (
                sale_date,
                str(row.get("sale_date", "") or sale_date),
                int(row.get("total_qty", 0) or 0),
                float(row.get("total_amount", 0) or 0),
            ),
        )

    for index, row in enumerate(category_rows, start=1):
        conn.execute(
            """
            INSERT INTO dashboard_category_summary (
                snapshot_date, rank, category_name, total_qty, total_amount
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                sale_date,
                index,
                str(row.get("category_name", "未分类") or "未分类"),
                int(row.get("total_qty", 0) or 0),
                float(row.get("total_amount", 0) or 0),
            ),
        )

    for index, row in enumerate(store_rows, start=1):
        conn.execute(
            """
            INSERT INTO dashboard_store_summary (
                snapshot_date, rank, store_name, total_qty, total_amount
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                sale_date,
                index,
                str(row.get("store_name", "") or ""),
                int(row.get("total_qty", 0) or 0),
                float(row.get("total_amount", 0) or 0),
            ),
        )

    for region_name, rows in region_top_rows.items():
        for index, row in enumerate(rows, start=1):
            code = str(row.get("product_code", "") or "")
            color = str(row.get("color_code", "") or "_")
            conn.execute(
                """
                INSERT INTO dashboard_region_top_products (
                    snapshot_date, region_name, rank, product_code, color_code, product_name, sales_qty, sales_amount, image_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sale_date,
                    region_name,
                    index,
                    code,
                    color,
                    str(row.get("product_name", "") or ""),
                    int(row.get("sales_qty", 0) or 0),
                    float(row.get("sales_amount", 0) or 0),
                    get_product_image(code, color).get("image_url", ""),
                ),
            )

    for row in matrix_rows:
        code = str(row.get("product_code", "") or "")
        conn.execute(
            """
            INSERT INTO dashboard_matrix (
                snapshot_date, rank, product_code, product_name, category_name, image_url,
                national_rank, national_qty, north_rank, north_qty, central_rank, central_qty, south_rank, south_qty
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sale_date,
                int(row.get("rank", 0) or 0),
                code,
                str(row.get("product_name", "") or ""),
                str(row.get("category_name", "") or ""),
                get_product_image(code).get("image_url", ""),
                int(row.get("national_rank", 0) or 0),
                int(row.get("national_qty", 0) or 0),
                row.get("north_rank"),
                int(row.get("north_qty", 0) or 0),
                row.get("central_rank"),
                int(row.get("central_qty", 0) or 0),
                row.get("south_rank"),
                int(row.get("south_qty", 0) or 0),
            ),
        )

    for row in sales_rows:
        code = str(row.get("product_code", "") or "")
        color = str(row.get("color_code", "") or "_")
        conn.execute(
            """
            INSERT INTO dashboard_sales_rows (
                snapshot_date, product_code, color_code, product_name, color_name, category_name,
                big_category_name, year, season_name, wave, designer_name, standard_price,
                sales_qty, sales_amount, sales_rows, image_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sale_date,
                code,
                color,
                str(row.get("product_name", "") or ""),
                str(row.get("color_name", "") or ""),
                str(row.get("category_name", "") or ""),
                str(row.get("big_category_name", "") or ""),
                str(row.get("year", "") or ""),
                str(row.get("season_name", "") or ""),
                str(row.get("wave", "") or ""),
                str(row.get("designer_name", "") or ""),
                float(row.get("standard_price", 0) or 0),
                int(row.get("sales_qty", 0) or 0),
                float(row.get("sales_amount", 0) or 0),
                int(row.get("sales_rows", 0) or 0),
                get_product_image(code, color).get("image_url", ""),
            ),
        )

    for index, row in enumerate([("inventory", "库存提醒", "建设中", "待补充库存联动规则"), ("slow_moving", "滞销商品", "建设中", "待补充滞销识别规则"), ("size_gap", "尺码断层风险", "建设中", "待补充尺码风险规则")], start=1):
        conn.execute(
            """
            INSERT INTO dashboard_alerts (
                snapshot_date, alert_order, alert_type, alert_title, alert_state, alert_text
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (sale_date, index, row[0], row[1], row[2], row[3]),
        )

def rebuild_dashboard_snapshot() -> dict[str, Any]:
    with get_db_connection() as conn:
        _ensure_tables(conn)
        dates = _snapshot_dates()
        for table in (
            "dashboard_snapshot",
            "dashboard_regions",
            "dashboard_top_products",
            "dashboard_color_top_products",
            "dashboard_category_summary",
            "dashboard_store_summary",
            "dashboard_daily_sales",
            "dashboard_region_top_products",
            "dashboard_matrix",
            "dashboard_sales_rows",
            "dashboard_alerts",
        ):
            conn.execute(f"DELETE FROM {table}")
        for sale_date in dates:
            _build_day(conn, sale_date)
        conn.commit()
    return {"snapshot_dates": dates, "rows": len(dates)}
