from flask import Blueprint, render_template

insights_bp = Blueprint("insights", __name__)


@insights_bp.route("/insights")
def insights_page():
    return render_template(
        "placeholder.html",
        active_page="insights",
        page_title="Insights",
        heading="Insights",
        message="Coming Soon",
    )
