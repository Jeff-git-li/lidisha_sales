from __future__ import annotations

from flask import Blueprint, render_template

from queries.data_center import load_data_center_raw
from semantic.data_center import build_data_center_summary


data_center_bp = Blueprint("data_center", __name__)


@data_center_bp.route("/data-center")
def data_center_page():
    raw = load_data_center_raw()
    summary = build_data_center_summary(raw)
    return render_template(
        "data_center.html",
        active_page="data_center",
        page_title="数据中心",
        summary=summary,
    )
