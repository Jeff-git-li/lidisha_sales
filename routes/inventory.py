from flask import Blueprint, render_template, request

from queries.inventory import get_inventory_analysis_context

inventory_bp = Blueprint("inventory", __name__)


@inventory_bp.route("/inventory")
def inventory_page():
    selected_scope = request.args.get("scope", "women").strip().lower() or "women"
    if selected_scope not in {"women", "all"}:
        selected_scope = "women"
    context = get_inventory_analysis_context(scope=selected_scope)
    return render_template(
        "inventory.html",
        active_page="inventory",
        page_title="库存分析",
        inventory_context=context.to_dict(),
        period=context.period.to_dict(),
        kpis=context.kpis.to_dict(),
        top_products=[item.to_dict() for item in context.top_products],
        warehouse_ranking=[item.to_dict() for item in context.warehouse_ranking],
        store_ranking=[item.to_dict() for item in context.store_ranking],
        region_summary=[item.to_dict() for item in context.region_summary],
        category_summary=[item.to_dict() for item in context.category_summary],
        wave_summary=[item.to_dict() for item in context.wave_summary],
        selected_scope=selected_scope,
    )
