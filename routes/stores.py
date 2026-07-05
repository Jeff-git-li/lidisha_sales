from flask import Blueprint, render_template

stores_bp = Blueprint("stores", __name__)


@stores_bp.route("/stores")
def stores_page():
    return render_template(
        "placeholder.html",
        active_page="stores",
        page_title="Stores",
        heading="Stores",
        message="Coming Soon",
    )
