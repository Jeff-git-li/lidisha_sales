from __future__ import annotations

from urllib.parse import urlencode

from flask import Blueprint, abort, render_template, request, url_for

from queries.products import EXPLORER_PAGE_SIZE, get_product_explorer, get_product_explorer_options
from queries.product_detail import get_product_detail


products_bp = Blueprint("products", __name__)

PRODUCT_FILTER_KEYS = (
    "year",
    "season_name",
    "wave",
    "brand_name",
    "designer_name",
    "category_name",
    "big_category_name",
    "series_name",
    "price_band",
    "color_name",
    "store_name",
)

SORT_OPTIONS = [
    {"value": "sales_qty", "label": "销量"},
    {"value": "sales_amount", "label": "销售额"},
    {"value": "average_price", "label": "客单价"},
    {"value": "store_coverage", "label": "门店覆盖数"},
    {"value": "standard_price", "label": "标准售价"},
    {"value": "newest", "label": "Newest Product"},
]

DISPLAY_MODES = [
    {"value": "cards", "label": "卡片"},
    {"value": "table", "label": "表格"},
    {"value": "gallery", "label": "图库"},
]


def _selected_values(args, key: str) -> list[str]:
    return [value for value in args.getlist(key) if value]


def _build_query_url(base_params: dict[str, str | int | list[str]], **overrides: str | int | list[str] | None) -> str:
    params = {key: value for key, value in base_params.items()}
    for key, value in overrides.items():
        if value in (None, ""):
            params.pop(key, None)
        else:
            params[key] = value
    query_string = urlencode(params, doseq=True)
    return f"{url_for('products.products_page')}?{query_string}" if query_string else url_for('products.products_page')


@products_bp.route("/products/<product_code>")
def product_detail(product_code: str):
    detail = get_product_detail(product_code)
    return render_template(
        "product_detail.html",
        active_page="products",
        page_title="商品详情",
        detail=detail,
    )


@products_bp.route("/products")
def products_page():
    selected_filters = {key: _selected_values(request.args, key) for key in PRODUCT_FILTER_KEYS}
    scope = request.args.get("scope", "women").strip().lower() or "women"
    if scope not in {"women", "all"}:
        scope = "women"
    search = request.args.get("q", "").strip()
    sort = request.args.get("sort", "sales_qty").strip() or "sales_qty"
    order = request.args.get("order", "desc").strip() or "desc"
    display_mode = request.args.get("mode", "cards").strip().lower() or "cards"
    if display_mode not in {option["value"] for option in DISPLAY_MODES}:
        display_mode = "cards"

    requested_page = max(1, int(request.args.get("page", 1) or 1))
    per_page = EXPLORER_PAGE_SIZE

    query_filters = {key: values for key, values in selected_filters.items() if values}
    if search:
        query_filters["search"] = [search]
    query_filters["scope"] = [scope]

    rows, total_count = get_product_explorer(
        filters=query_filters,
        sort=sort,
        order=order,
        page=requested_page,
        per_page=per_page,
    )
    total_pages = max(1, (total_count + per_page - 1) // per_page) if total_count else 1
    page = min(requested_page, total_pages)
    if page != requested_page:
        rows, total_count = get_product_explorer(
            filters=query_filters,
            sort=sort,
            order=order,
            page=page,
            per_page=per_page,
        )

    options = get_product_explorer_options()

    base_params: dict[str, str | int | list[str]] = {key: value for key, value in query_filters.items() if value}
    if search:
        base_params["q"] = search
    base_params["sort"] = sort
    base_params["order"] = order
    base_params["mode"] = display_mode
    base_params["page"] = page

    mode_links = {
        option["value"]: _build_query_url(base_params, mode=option["value"], page=1)
        for option in DISPLAY_MODES
    }

    page_numbers: list[int] = []
    if total_pages <= 7:
        page_numbers = list(range(1, total_pages + 1))
    else:
        page_numbers = sorted({1, 2, page - 1, page, page + 1, total_pages - 1, total_pages})
        page_numbers = [number for number in page_numbers if 1 <= number <= total_pages]

    pagination_links = []
    previous_number = None
    for number in page_numbers:
        if previous_number is not None and number - previous_number > 1:
            pagination_links.append({"ellipsis": True})
        pagination_links.append({"page": number, "url": _build_query_url(base_params, page=number)})
        previous_number = number

    prev_url = _build_query_url(base_params, page=max(1, page - 1)) if page > 1 else url_for("products.products_page")
    next_url = _build_query_url(base_params, page=min(total_pages, page + 1)) if page < total_pages else url_for("products.products_page")

    return render_template(
        "products.html",
        active_page="products",
        page_title="商品分析",
        rows=rows,
        selected_filters=selected_filters,
        search_query=search,
        sort_value=sort,
        order_value=order,
        display_mode=display_mode,
        total_count=total_count,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        pagination_links=pagination_links,
        mode_links=mode_links,
        prev_url=prev_url,
        next_url=next_url,
        sort_options=SORT_OPTIONS,
        display_modes=DISPLAY_MODES,
        options=options,
        query_action=url_for("products.products_page"),
        scope=scope,
    )
