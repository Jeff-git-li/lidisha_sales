from flask import Blueprint, render_template

regions_bp = Blueprint("regions", __name__)


@regions_bp.route("/regions")
def regions_page():
    return render_template(
        "placeholder.html",
        active_page="regions",
        page_title="区域分析",
        heading="区域分析",
        message="敬请期待",
    )
