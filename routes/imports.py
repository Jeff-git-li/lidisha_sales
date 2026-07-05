from flask import Blueprint, render_template

imports_bp = Blueprint("imports", __name__)


@imports_bp.route("/imports")
def imports_page():
    return render_template(
        "placeholder.html",
        active_page="imports",
        page_title="Imports",
        heading="Imports",
        message="Coming Soon",
    )
