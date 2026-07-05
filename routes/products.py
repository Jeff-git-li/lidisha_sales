from flask import Blueprint, render_template

from queries.top20 import get_top20_products

products_bp = Blueprint("products", __name__)


@products_bp.route("/products")
def products_page():
    rows = get_top20_products()
    return render_template(
        "products.html",
        active_page="products",
        page_title="Products",
        rows=rows,
    )
