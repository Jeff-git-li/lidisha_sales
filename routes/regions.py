from flask import Blueprint, render_template

regions_bp = Blueprint("regions", __name__)


@regions_bp.route("/regions")
def regions_page():
    return render_template(
        "placeholder.html",
        active_page="regions",
        page_title="Regions",
        heading="Regions",
        message="Coming Soon",
    )
