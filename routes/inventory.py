from flask import Blueprint, render_template, request

from queries.inventory import get_inventory_analysis_context

inventory_bp = Blueprint("inventory", __name__)


@inventory_bp.route("/inventory")
def inventory_page():
    selected_scope = request.args.get("scope", "women").strip().lower() or "women"
    if selected_scope not in {"women", "all"}:
        selected_scope = "women"
    selected_channel_code = request.args.get("channel_code", request.args.get("channel", "")).strip()
    selected_store_code = request.args.get("store_code", request.args.get("store", "")).strip()
    context = get_inventory_analysis_context(scope=selected_scope, channel_code=selected_channel_code, store_code=selected_store_code)
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
        health_summary=[item.to_dict() for item in context.health_summary],
        selected_scope=selected_scope,
        selected_channel_code=context.selected_channel_code,
        selected_channel_name=context.selected_channel_name,
        selected_store_code=context.selected_store_code,
        selected_store_name=context.selected_store_name,
        channel_options=[item.to_dict() for item in context.channel_options],
        store_options=[item.to_dict() for item in context.store_options],
        data_quality_note=context.data_quality_note,
        filter_warning=context.filter_warning,
    )
