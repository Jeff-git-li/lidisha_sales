from __future__ import annotations

from flask import Blueprint, render_template, request

from queries.quarter import get_available_quarters, get_quarter_analysis_context


quarter_bp = Blueprint("quarter", __name__)


@quarter_bp.route("/quarter")
def quarter_page():
    selected_year = request.args.get("selected_year", type=int)
    selected_quarter = request.args.get("selected_quarter", type=int)
    scope = request.args.get("scope")
    context = get_quarter_analysis_context(selected_year, selected_quarter, scope=scope)
    availability = get_available_quarters()
    return render_template(
        "quarter.html",
        active_page="quarter",
        page_title="季度分析",
        quarter_context=context.to_dict(),
        period=context.period.to_dict(),
        kpis=context.kpis.to_dict(),
        comparisons=[item.to_dict() for item in context.comparisons],
        top_products=[item.to_dict() for item in context.top_products],
        region_summary=[item.to_dict() for item in context.region_summary],
        category_summary=[item.to_dict() for item in context.category_summary],
        wave_summary=[item.to_dict() for item in context.wave_summary],
        available_years=availability["available_years"],
        available_quarters=availability["available_quarters"],
        selected_year=context.period.selected_year,
        selected_quarter=context.period.selected_quarter,
    )
