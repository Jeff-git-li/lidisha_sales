from flask import Blueprint, render_template, request

from queries.inventory import get_inventory_analysis_context

inventory_bp = Blueprint("inventory", __name__)


@inventory_bp.route("/inventory")
def inventory_page():
    selected_scope = request.args.get("scope", "women").strip().lower() or "women"
    if selected_scope not in {"women", "all"}:
        selected_scope = "women"
    selected_inventory_basis = request.args.get("inventory_basis", "terminal").strip().lower() or "terminal"
    selected_product_sort = request.args.get("product_sort", "quarter_sales_qty").strip().lower() or "quarter_sales_qty"
    selected_channel_code = request.args.get("channel_code", request.args.get("channel", "")).strip()
    selected_store_code = request.args.get("store_code", request.args.get("store", "")).strip()
    context = get_inventory_analysis_context(
        scope=selected_scope,
        channel_code=selected_channel_code,
        store_code=selected_store_code,
        inventory_basis=selected_inventory_basis,
        product_sort=selected_product_sort,
    )
    return render_template(
        "inventory.html",
        active_page="inventory",
        page_title="库存分析",
        inventory_context=context.to_dict(),
        period=context.period.to_dict(),
        kpis=context.kpis.to_dict(),
        top_products=[item.to_dict() for item in context.top_products],
        sellthrough_products=[item.to_dict() for item in context.sellthrough_products],
        warehouse_ranking=[item.to_dict() for item in context.warehouse_ranking],
        store_ranking=[item.to_dict() for item in context.store_ranking],
        region_summary=[item.to_dict() for item in context.region_summary],
        category_summary=[item.to_dict() for item in context.category_summary],
        health_summary=[item.to_dict() for item in context.health_summary],
        selected_scope=selected_scope,
        selected_inventory_basis=context.selected_inventory_basis,
        inventory_basis_label=context.inventory_basis_label,
        selected_channel_code=context.selected_channel_code,
        selected_channel_name=context.selected_channel_name,
        selected_store_code=context.selected_store_code,
        selected_store_name=context.selected_store_name,
        selected_product_sort=context.selected_product_sort,
        channel_options=[item.to_dict() for item in context.channel_options],
        store_options=[item.to_dict() for item in context.store_options],
        data_quality_note=context.data_quality_note,
        filter_warning=context.filter_warning,
    )
