from __future__ import annotations

from flask import Blueprint, render_template, request

from queries.store import load_store_analysis_raw
from semantic.store import build_store_analysis_context


store_bp = Blueprint("store", __name__)


@store_bp.route("/stores")
def store_page():
    selected_store_code = request.args.get("store_code", "").strip()
    raw = load_store_analysis_raw(selected_store_code=selected_store_code)
    context = build_store_analysis_context(raw)
    return render_template(
        "store.html",
        active_page="stores",
        page_title="门店分析",
        store_context=context.to_dict(),
        period=context.period.to_dict(),
        kpis=context.kpis.to_dict(),
        health_summary=[item.to_dict() for item in context.health_summary],
        top_stores=[item.to_dict() for item in context.top_stores],
        bottom_stores=[item.to_dict() for item in context.bottom_stores],
        trend_placeholder=None if context.trend_placeholder is None else context.trend_placeholder.to_dict(),
        selected_store_code=context.selected_store_code,
        selected_store_name=context.selected_store_name,
        selected_store_detail=None if context.selected_store_detail is None else context.selected_store_detail.to_dict(),
        data_quality_note=context.data_quality_note,
        filter_warning=context.filter_warning,
    )