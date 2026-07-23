from flask import Blueprint, redirect, url_for

imports_bp = Blueprint("imports", __name__)


@imports_bp.route("/imports")
def imports_page():
    return redirect(url_for("data_center.data_center_page"))
