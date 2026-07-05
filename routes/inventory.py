from flask import Blueprint, render_template

inventory_bp = Blueprint("inventory", __name__)


@inventory_bp.route("/inventory")
def inventory_page():
    return render_template(
        "placeholder.html",
        active_page="inventory",
        page_title="Inventory",
        heading="Inventory",
        message="Coming Soon",
    )
