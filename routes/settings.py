from flask import Blueprint, render_template

settings_bp = Blueprint("settings", __name__)


@settings_bp.route("/settings")
def settings_page():
    return render_template(
        "placeholder.html",
        active_page="settings",
        page_title="系统设置",
        heading="系统设置",
        message="敬请期待",
    )
