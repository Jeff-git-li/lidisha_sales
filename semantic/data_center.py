from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from config import AUTO_REFRESH_HOUR, AUTO_REFRESH_MINUTE


SALES_HEALTHY_DAYS = 2
SALES_WARNING_DAYS = 5
INVENTORY_HEALTHY_DAYS = 7
INVENTORY_WARNING_DAYS = 14
LOCK_ACTIVE_THRESHOLD_SECONDS = 30 * 60
LOCK_STALE_THRESHOLD_SECONDS = 2 * 60 * 60
HISTORY_MESSAGE_LIMIT = 120


def _safe_int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _format_number(value: Any) -> str:
    return f"{_safe_int(value):,}"


def _format_quantity(value: Any, suffix: str = "") -> str:
    return f"{_safe_float(value):,.0f}{suffix}"


def _format_amount(value: Any) -> str:
    return f"¥{_safe_float(value):,.2f}"


def _format_date(value: str | None) -> str:
    parsed = _parse_date(value)
    if not parsed:
        return "--"
    return parsed.isoformat()


def _format_datetime(value: str | None) -> str:
    parsed = _parse_datetime(value)
    if not parsed:
        return "--"
    return parsed.strftime("%Y-%m-%d %H:%M")


def _short_text(value: str, limit: int = HISTORY_MESSAGE_LIMIT) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1].rstrip()}…"


def _filename(value: str | None) -> str:
    if not value:
        return "--"
    return Path(value).name


def _days_behind(latest_value: str | None) -> int | None:
    latest_date = _parse_date(latest_value)
    if not latest_date:
        return None
    delta = date.today() - latest_date
    return max(0, delta.days)


def _freshness_label(days_behind: int | None) -> str:
    if days_behind is None:
        return "Unknown"
    if days_behind == 0:
        return "Current"
    if days_behind == 1:
        return "1 day behind"
    return f"{days_behind} days behind"


def _freshness_state(days_behind: int | None, healthy_days: int, warning_days: int) -> str:
    if days_behind is None:
        return "Unknown"
    if days_behind <= healthy_days:
        return "Healthy"
    if days_behind <= warning_days:
        return "Warning"
    return "Critical"


def _status_class(status: str) -> str:
    return {
        "Healthy": "success",
        "Warning": "warning",
        "Critical": "danger",
        "Unknown": "secondary",
    }.get(status, "secondary")


def _status_rank(status: str) -> int:
    return {
        "Unknown": 0,
        "Healthy": 1,
        "Warning": 2,
        "Critical": 3,
    }.get(status, 0)


def _import_status_class(status: str) -> str:
    return {
        "Success": "success",
        "Failed": "danger",
        "Skipped": "secondary",
        "Running": "warning",
        "Unknown": "secondary",
    }.get(status, "secondary")


def _severity_to_class(severity: str) -> str:
    return {
        "Critical": "danger",
        "Warning": "warning",
        "Info": "info",
        "Unknown": "secondary",
    }.get(severity, "secondary")


def _lock_state(age_seconds: float | None) -> tuple[str, str]:
    if age_seconds is None:
        return "Unknown", "Lock age unavailable"
    if age_seconds <= LOCK_ACTIVE_THRESHOLD_SECONDS:
        return "Active", f"Age {int(age_seconds // 60)} min"
    if age_seconds <= LOCK_STALE_THRESHOLD_SECONDS:
        return "Possibly stale", f"Age {int(age_seconds // 60)} min"
    return "Possibly stale", f"Age {int(age_seconds // 60)} min"


@dataclass(slots=True)
class DataHealthStatus:
    status: str
    label: str
    explanation: str
    relevant_value: str = ""
    css_class: str = "secondary"

    @classmethod
    def from_parts(cls, status: str, explanation: str, relevant_value: str = "") -> "DataHealthStatus":
        return cls(
            status=status,
            label=status,
            explanation=explanation,
            relevant_value=relevant_value,
            css_class=_status_class(status),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SalesDataStatus:
    latest_sales_date: str
    earliest_sales_date: str
    total_rows: str
    unique_products: str
    unique_stores: str
    last_successful_daily_sales_import: str
    last_successful_filename: str
    last_failed_daily_sales_import: str
    last_failed_filename: str
    last_imported_filename: str
    last_imported_row_count: str
    daily_queue_folder_file_count: str
    daily_queue_pending_file_count: str
    daily_queue_skipped_or_processed_file_count: str
    duplicate_skipped_file_count: str
    failed_daily_file_count: str
    freshness_label: str
    freshness_state: str
    freshness_detail: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class InventoryDataStatus:
    latest_inventory_date: str
    total_rows: str
    total_quantity: str
    unique_products: str
    unique_warehouses: str
    terminal_inventory_quantity: str
    all_inventory_quantity: str
    last_inventory_import_time: str
    current_source_filename: str
    freshness_label: str
    freshness_state: str
    freshness_detail: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class MasterDataStatus:
    product_count: str
    store_count: str
    warehouse_count: str
    channel_count: str
    products_missing_category: str
    stores_missing_channel: str
    inventory_warehouse_codes_not_mapped_to_dim_store: str
    sales_product_codes_not_mapped_to_dim_product: str
    sales_store_codes_not_mapped_to_dim_store: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SnapshotStatus:
    latest_snapshot_date: str
    latest_snapshot_build_time: str
    snapshot_row_count: str
    snapshot_date_coverage: str
    last_snapshot_result: str
    behind_latest_sales_date: str
    rebuild_required: str
    freshness_label: str
    freshness_state: str
    freshness_detail: str
    latest_data_date: str
    snapshot_total_qty: str
    snapshot_total_amount: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ImportHistoryItem:
    time: str
    import_type: str
    filename: str
    status: str
    rows_read: str
    rows_imported: str
    rows_rejected: str
    duplicates: str
    duration: str
    message_short: str
    message_full: str
    status_class: str
    source_kind: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class OperationalAlert:
    severity: str
    title: str
    explanation: str
    relevant_value: str
    recommended_action: str
    severity_class: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SchedulerStatus:
    state: str
    label: str
    detail: str
    thread_name: str
    schedule_label: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DataCenterSummary:
    generated_at: str
    response_time_ms: str
    section_timings: dict[str, str]
    overall: DataHealthStatus
    sales: SalesDataStatus
    inventory: InventoryDataStatus
    master: MasterDataStatus
    snapshot: SnapshotStatus
    import_history: list[ImportHistoryItem]
    alerts: list[OperationalAlert]
    queue_directory: str
    queue_folder_file_count: str
    queue_pending_file_count: str
    queue_skipped_or_processed_file_count: str
    queue_files: list[dict[str, Any]]
    lock_status: str
    lock_detail: str
    lock_age: str
    scheduler: SchedulerStatus
    last_refresh_time: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["overall"] = self.overall.to_dict()
        payload["sales"] = self.sales.to_dict()
        payload["inventory"] = self.inventory.to_dict()
        payload["master"] = self.master.to_dict()
        payload["snapshot"] = self.snapshot.to_dict()
        payload["import_history"] = [item.to_dict() for item in self.import_history]
        payload["alerts"] = [item.to_dict() for item in self.alerts]
        payload["scheduler"] = self.scheduler.to_dict()
        return payload


def _freshness_display(latest_value: str | None, healthy_days: int, warning_days: int) -> tuple[str, str, str]:
    days_behind = _days_behind(latest_value)
    label = _freshness_label(days_behind)
    state = _freshness_state(days_behind, healthy_days, warning_days)
    if days_behind is None:
        detail = "Freshness cannot be determined"
    elif days_behind == 0:
        detail = "Current as of today"
    else:
        detail = f"{days_behind} calendar day{'s' if days_behind != 1 else ''} behind"
    return label, state, detail


def _build_history_items(raw_history: list[dict[str, Any]]) -> list[ImportHistoryItem]:
    items: list[ImportHistoryItem] = []
    for row in raw_history:
        status = str(row.get("status", "") or "Unknown")
        message_full = str(row.get("message", "") or "")
        if not message_full and status == "Success":
            message_full = "文件已成功导入"
        elif not message_full and status == "Skipped":
            message_full = "文件已跳过"
        elif not message_full:
            message_full = "暂无消息"
        duration_seconds = row.get("duration_seconds")
        if duration_seconds is None or duration_seconds == "":
            duration_text = "--"
        else:
            try:
                duration_text = f"{float(duration_seconds):.2f}s"
            except (TypeError, ValueError):
                duration_text = "--"
        items.append(
            ImportHistoryItem(
                time=_format_datetime(row.get("time")),
                import_type=str(row.get("import_type", "") or "sales"),
                filename=_filename(row.get("filename")),
                status=status,
                rows_read=_format_number(row.get("rows_read")),
                rows_imported=_format_number(row.get("rows_imported")),
                rows_rejected=_format_number(row.get("rows_rejected")),
                duplicates=_format_number(row.get("duplicates")),
                duration=duration_text,
                message_short=_short_text(message_full),
                message_full=message_full,
                status_class=_import_status_class(status),
                source_kind=str(row.get("source_kind", "") or ""),
            )
        )
    return items


def _build_queue_items(raw_queue_files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in raw_queue_files:
        items.append(
            {
                "filename": str(row.get("filename", "") or "--"),
                "sha256": str(row.get("sha256", "") or ""),
                "registry_status": str(row.get("registry_status", "") or "Unknown"),
                "imported_at": _format_datetime(row.get("imported_at")),
                "pending": "Yes" if bool(row.get("pending", False)) else "No",
                "pending_bool": bool(row.get("pending", False)),
                "next_action": str(row.get("next_action", "") or "skipped"),
                "next_action_label": str(row.get("next_action_label", "") or "skipped"),
                "next_action_class": str(row.get("next_action_class", "secondary") or "secondary"),
                "registry_status_class": _import_status_class(str(row.get("registry_status", "") or "Unknown")),
            }
        )
    return items


def _build_alerts(raw: dict[str, Any], overall_status: str) -> list[OperationalAlert]:
    alerts: list[OperationalAlert] = []
    sales = raw["sales"]
    inventory = raw["inventory"]
    master = raw["master"]
    snapshot = raw["snapshot"]
    pending_file_count = _safe_int(raw["queue"].get("pending_file_count"))
    lock_status = raw["lock"]["state"]

    if pending_file_count > 0:
        alerts.append(
            OperationalAlert(
                severity="Warning",
                title=f"{pending_file_count} daily sales files are waiting",
                explanation="Files in exports/sales/daily still require processing on the next refresh.",
                relevant_value=f"{pending_file_count} files",
                recommended_action="Run Refresh Data to import pending files.",
                severity_class=_severity_to_class("Warning"),
            )
        )

    if str(snapshot.get("rebuild_required", "False")).lower() == "true":
        alerts.append(
            OperationalAlert(
                severity="Warning",
                title="The snapshot is behind the latest sales date",
                explanation="The dashboard snapshot has not caught up with the current sales data.",
                relevant_value=snapshot.get("latest_data_date", "") or "--",
                recommended_action="Run Refresh Data to rebuild the snapshot.",
                severity_class=_severity_to_class("Warning"),
            )
        )

    inventory_state = inventory.get("freshness_state", "Unknown")
    if inventory_state in {"Warning", "Critical"}:
        alerts.append(
            OperationalAlert(
                severity=inventory_state,
                title="Inventory data is older than sales data",
                explanation="Inventory freshness is behind the current sales feed.",
                relevant_value=f"{inventory.get('freshness_label', 'Unknown')} / {inventory.get('latest_inventory_date', '--')}",
                recommended_action="Review the latest inventory export and refresh the dashboard.",
                severity_class=_severity_to_class(inventory_state),
            )
        )

    if lock_status in {"Active", "Possibly stale"}:
        severity = "Warning" if lock_status == "Active" else "Critical"
        alerts.append(
            OperationalAlert(
                severity=severity,
                title="A stale import lock may be blocking updates" if lock_status == "Possibly stale" else "An import lock is currently active",
                explanation="The daily import lock file exists and the refresh workflow will not overlap.",
                relevant_value=raw["lock"].get("age_label", "--"),
                recommended_action="Wait for the running import to finish or inspect the lock file age.",
                severity_class=_severity_to_class(severity),
            )
        )

    if _safe_int(master.get("sales_product_codes_not_mapped_to_dim_product")) > 0:
        count = _safe_int(master.get("sales_product_codes_not_mapped_to_dim_product"))
        alerts.append(
            OperationalAlert(
                severity="Warning",
                title="Sales rows reference unknown products",
                explanation="Some sales product codes do not map to the product dimension.",
                relevant_value=f"{count} products",
                recommended_action="Review product master data and mapping rules.",
                severity_class=_severity_to_class("Warning"),
            )
        )

    if _safe_int(master.get("sales_store_codes_not_mapped_to_dim_store")) > 0:
        count = _safe_int(master.get("sales_store_codes_not_mapped_to_dim_store"))
        alerts.append(
            OperationalAlert(
                severity="Warning",
                title="Sales rows reference unknown stores",
                explanation="Some sales store codes do not map to the store dimension.",
                relevant_value=f"{count} stores",
                recommended_action="Review store master data and channel mappings.",
                severity_class=_severity_to_class("Warning"),
            )
        )

    if _safe_int(master.get("inventory_warehouse_codes_not_mapped_to_dim_store")) > 0:
        count = _safe_int(master.get("inventory_warehouse_codes_not_mapped_to_dim_store"))
        alerts.append(
            OperationalAlert(
                severity="Warning",
                title="Inventory warehouses are not mapped to stores",
                explanation="Some warehouse codes do not map to store records.",
                relevant_value=f"{count} warehouses",
                recommended_action="Review warehouse-to-store mapping in master data.",
                severity_class=_severity_to_class("Warning"),
            )
        )

    if not alerts and overall_status == "Healthy":
        alerts.append(
            OperationalAlert(
                severity="Info",
                title="No current operational alerts",
                explanation="Sales, inventory, snapshot, and queue status are all within expected ranges.",
                relevant_value="All clear",
                recommended_action="No action required.",
                severity_class=_severity_to_class("Info"),
            )
        )

    return alerts


def _build_overall_status(raw: dict[str, Any]) -> DataHealthStatus:
    sales = raw["sales"]
    inventory = raw["inventory"]
    master = raw["master"]
    snapshot = raw["snapshot"]
    lock = raw["lock"]
    pending_file_count = _safe_int(raw["queue"].get("pending_file_count"))

    if not sales.get("available") or not inventory.get("available") or not master.get("available") or not snapshot.get("available"):
        return DataHealthStatus.from_parts("Unknown", "One or more operational metadata sources are unavailable.")
    if _safe_int(sales.get("total_rows")) <= 0:
        return DataHealthStatus.from_parts("Critical", "No sales data is available.")
    if _safe_int(inventory.get("total_rows")) <= 0:
        return DataHealthStatus.from_parts("Critical", "No inventory data is available.")
    if lock.get("state") == "Possibly stale":
        return DataHealthStatus.from_parts("Critical", "A stale import lock may be blocking updates.", lock.get("age_label", ""))
    if str(snapshot.get("rebuild_required", "False")).lower() == "true":
        return DataHealthStatus.from_parts("Warning", "The dashboard snapshot is behind the latest sales data.", snapshot.get("latest_data_date", ""))
    sales_state = str(sales.get("freshness_state", "Unknown"))
    inventory_state = str(inventory.get("freshness_state", "Unknown"))
    if "Critical" in {sales_state, inventory_state}:
        return DataHealthStatus.from_parts("Critical", "At least one core dataset is critically stale.")
    if "Warning" in {sales_state, inventory_state}:
        return DataHealthStatus.from_parts("Warning", "At least one core dataset needs attention.")
    if pending_file_count > 0:
        return DataHealthStatus.from_parts("Warning", f"{pending_file_count} daily sales files are waiting in the queue.")
    if _safe_int(master.get("sales_product_codes_not_mapped_to_dim_product")) > 0 or _safe_int(master.get("sales_store_codes_not_mapped_to_dim_store")) > 0 or _safe_int(master.get("inventory_warehouse_codes_not_mapped_to_dim_store")) > 0:
        return DataHealthStatus.from_parts("Warning", "There are master-data mapping gaps to review.")
    return DataHealthStatus.from_parts("Healthy", "Sales, inventory, snapshot, and queue state are all current.")


def build_data_center_summary(raw: dict[str, Any]) -> DataCenterSummary:
    sales = raw["sales"]
    inventory = raw["inventory"]
    master = raw["master"]
    snapshot = raw["snapshot"]
    lock = raw["lock"]
    scheduler = raw["scheduler"]

    sales_freshness_label, sales_freshness_state, sales_freshness_detail = _freshness_display(sales.get("latest_sales_date"), SALES_HEALTHY_DAYS, SALES_WARNING_DAYS)
    inventory_freshness_label, inventory_freshness_state, inventory_freshness_detail = _freshness_display(inventory.get("latest_inventory_date"), INVENTORY_HEALTHY_DAYS, INVENTORY_WARNING_DAYS)

    lock_state, lock_detail = _lock_state(lock.get("age_seconds"))
    lock_age = "--" if lock.get("age_seconds") is None else f"{int(_safe_float(lock.get('age_seconds')) // 60)} min"
    if not lock.get("exists"):
        lock_state = "Free"
        lock_detail = "No import lock file is present"

    latest_refresh_time = raw.get("latest_successful_refresh_time", "") or snapshot.get("latest_snapshot_build_time", "")
    if not latest_refresh_time:
        latest_refresh_time = raw.get("generated_at", "")

    overall = _build_overall_status(raw)
    alerts = _build_alerts(raw, overall.status)
    history_items = _build_history_items(raw.get("history", []))
    queue_items = _build_queue_items(raw.get("queue", {}).get("files", []))

    latest_snapshot_date = str(snapshot.get("latest_snapshot_date", "") or "")
    latest_snapshot_date_display = _format_date(latest_snapshot_date)
    latest_snapshot_build_time = _format_datetime(snapshot.get("latest_snapshot_build_time"))
    snapshot_date_coverage = str(snapshot.get("snapshot_date_coverage", "") or "Unknown")
    last_snapshot_result = str(snapshot.get("last_snapshot_result", "") or "Unknown")
    snapshot_status = "Unknown"
    if snapshot.get("available"):
        if str(snapshot.get("rebuild_required", "False")).lower() == "true":
            snapshot_status = "Warning"
        elif latest_snapshot_date:
            snapshot_status = "Healthy"
    snapshot_freshness_label = "Unknown"
    snapshot_freshness_detail = "Snapshot freshness cannot be determined"
    if latest_snapshot_date:
        snapshot_days = _days_behind(latest_snapshot_date)
        snapshot_freshness_label = _freshness_label(snapshot_days)
        snapshot_freshness_detail = "Current as of today" if snapshot_days == 0 else (f"{snapshot_days} calendar day{'s' if snapshot_days != 1 else ''} behind" if snapshot_days is not None else "Snapshot freshness cannot be determined")

    return DataCenterSummary(
        generated_at=_format_datetime(raw.get("generated_at")),
        response_time_ms="--",
        section_timings={key: f"{value:.0f} ms" for key, value in raw.get("timings", {}).items()},
        overall=overall,
        sales=SalesDataStatus(
            latest_sales_date=_format_date(sales.get("latest_sales_date")),
            earliest_sales_date=_format_date(sales.get("earliest_sales_date")),
            total_rows=_format_number(sales.get("total_rows")),
            unique_products=_format_number(sales.get("unique_products")),
            unique_stores=_format_number(sales.get("unique_stores")),
            last_successful_daily_sales_import=_format_datetime(sales.get("last_successful_daily_sales_import")),
            last_successful_filename=_filename(sales.get("last_successful_filename")),
            last_failed_daily_sales_import=_format_datetime(sales.get("last_failed_daily_sales_import")),
            last_failed_filename=_filename(sales.get("last_failed_filename")),
            last_imported_filename=_filename(sales.get("last_imported_filename")),
            last_imported_row_count=_format_number(sales.get("last_imported_row_count")),
            daily_queue_folder_file_count=_format_number(sales.get("queue_folder_file_count")),
            daily_queue_pending_file_count=_format_number(sales.get("queue_pending_file_count")),
            daily_queue_skipped_or_processed_file_count=_format_number(sales.get("queue_skipped_or_processed_file_count")),
            duplicate_skipped_file_count=_format_number(sales.get("duplicate_skipped_file_count")),
            failed_daily_file_count=_format_number(sales.get("failed_daily_file_count")),
            freshness_label=sales_freshness_label,
            freshness_state=sales_freshness_state,
            freshness_detail=sales_freshness_detail,
        ),
        inventory=InventoryDataStatus(
            latest_inventory_date=_format_date(inventory.get("latest_inventory_date")),
            total_rows=_format_number(inventory.get("total_rows")),
            total_quantity=_format_quantity(inventory.get("total_inventory_quantity"), " 件"),
            unique_products=_format_number(inventory.get("unique_products")),
            unique_warehouses=_format_number(inventory.get("unique_warehouses")),
            terminal_inventory_quantity=_format_quantity(inventory.get("terminal_inventory_quantity"), " 件"),
            all_inventory_quantity=_format_quantity(inventory.get("all_inventory_quantity"), " 件"),
            last_inventory_import_time=_format_datetime(inventory.get("last_inventory_import_time")),
            current_source_filename=_filename(inventory.get("current_source_filename")),
            freshness_label=inventory_freshness_label,
            freshness_state=inventory_freshness_state,
            freshness_detail=inventory_freshness_detail,
        ),
        master=MasterDataStatus(
            product_count=_format_number(master.get("product_count")),
            store_count=_format_number(master.get("store_count")),
            warehouse_count=_format_number(master.get("warehouse_count")),
            channel_count=_format_number(master.get("channel_count")),
            products_missing_category=_format_number(master.get("products_missing_category")),
            stores_missing_channel=_format_number(master.get("stores_missing_channel")),
            inventory_warehouse_codes_not_mapped_to_dim_store=_format_number(master.get("inventory_warehouse_codes_not_mapped_to_dim_store")),
            sales_product_codes_not_mapped_to_dim_product=_format_number(master.get("sales_product_codes_not_mapped_to_dim_product")),
            sales_store_codes_not_mapped_to_dim_store=_format_number(master.get("sales_store_codes_not_mapped_to_dim_store")),
        ),
        snapshot=SnapshotStatus(
            latest_snapshot_date=latest_snapshot_date_display,
            latest_snapshot_build_time=latest_snapshot_build_time,
            snapshot_row_count=_format_number(snapshot.get("snapshot_row_count")),
            snapshot_date_coverage=snapshot_date_coverage,
            last_snapshot_result=last_snapshot_result,
            behind_latest_sales_date="Yes" if str(snapshot.get("behind_latest_sales_date", False)).lower() == "true" else "No",
            rebuild_required="Yes" if str(snapshot.get("rebuild_required", False)).lower() == "true" else "No",
            freshness_label=snapshot_freshness_label,
            freshness_state=snapshot_status,
            freshness_detail=snapshot_freshness_detail,
            latest_data_date=_format_date(snapshot.get("latest_data_date")),
            snapshot_total_qty=_format_quantity(snapshot.get("snapshot_total_qty"), " 件"),
            snapshot_total_amount=_format_amount(snapshot.get("snapshot_total_amount")),
        ),
        import_history=history_items,
        alerts=alerts,
        queue_directory=str(raw.get("queue", {}).get("directory", "exports/sales/daily") or "exports/sales/daily"),
        queue_folder_file_count=_format_number(raw.get("queue", {}).get("folder_file_count")),
        queue_pending_file_count=_format_number(raw.get("queue", {}).get("pending_file_count")),
        queue_skipped_or_processed_file_count=_format_number(raw.get("queue", {}).get("skipped_or_processed_file_count")),
        queue_files=queue_items,
        lock_status=lock_state,
        lock_detail=lock_detail,
        lock_age=lock_age,
        scheduler=SchedulerStatus(
            state="Running" if scheduler.get("running") else "Idle",
            label="运行中" if scheduler.get("running") else "空闲",
            detail=f"{scheduler.get('schedule_label', f'每天 {AUTO_REFRESH_HOUR:02d}:{AUTO_REFRESH_MINUTE:02d}')}",
            thread_name=str(scheduler.get("thread_name", "daily-auto-refresh") or "daily-auto-refresh"),
            schedule_label=str(scheduler.get("schedule_label", f"每天 {AUTO_REFRESH_HOUR:02d}:{AUTO_REFRESH_MINUTE:02d}")),
        ),
        last_refresh_time=_format_datetime(latest_refresh_time),
    )
