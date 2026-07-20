from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


def _as_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _as_int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


@dataclass(slots=True)
class InventoryPeriod:
    inventory_date: str
    label: str

    @classmethod
    def from_query_row(cls, row: Mapping[str, Any]) -> "InventoryPeriod":
        return cls(
            inventory_date=str(row.get("inventory_date", "") or ""),
            label=str(row.get("label", "") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class InventoryKPI:
    current_inventory_amount: float = 0.0
    current_inventory_qty: float = 0.0
    inventory_sku_count: int = 0
    warehouse_count: int = 0
    store_warehouse_count: int = 0
    last_30_days_sales: float | None = None
    sell_through_rate: float | None = None
    inventory_days: float | None = None
    sales_available: bool = False

    @classmethod
    def from_query_row(cls, row: Mapping[str, Any]) -> "InventoryKPI":
        return cls(
            current_inventory_amount=_as_float(row.get("current_inventory_amount")),
            current_inventory_qty=_as_float(row.get("current_inventory_qty")),
            inventory_sku_count=_as_int(row.get("inventory_sku_count")),
            warehouse_count=_as_int(row.get("warehouse_count")),
            store_warehouse_count=_as_int(row.get("store_warehouse_count")),
            last_30_days_sales=(None if row.get("last_30_days_sales") is None else _as_float(row.get("last_30_days_sales"))),
            sell_through_rate=(None if row.get("sell_through_rate") is None else _as_float(row.get("sell_through_rate"))),
            inventory_days=(None if row.get("inventory_days") is None else _as_float(row.get("inventory_days"))),
            sales_available=bool(row.get("sales_available", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class InventoryTopProduct:
    rank: int
    product_code: str
    product_name: str
    image_url: str = ""
    inventory_qty: float = 0.0
    inventory_amount: float = 0.0
    warehouse_coverage: int = 0
    average_cost: float = 0.0

    @classmethod
    def from_query_row(cls, row: Mapping[str, Any]) -> "InventoryTopProduct":
        return cls(
            rank=_as_int(row.get("rank")),
            product_code=str(row.get("product_code", "") or ""),
            product_name=str(row.get("product_name", "") or ""),
            image_url=str(row.get("image_url", "") or ""),
            inventory_qty=_as_float(row.get("inventory_qty")),
            inventory_amount=_as_float(row.get("inventory_amount")),
            warehouse_coverage=_as_int(row.get("warehouse_coverage")),
            average_cost=_as_float(row.get("average_cost")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class InventoryWarehouseSummary:
    rank: int
    warehouse_code: str
    warehouse_name: str
    warehouse_type: str
    inventory_amount: float = 0.0
    inventory_qty: float = 0.0
    sku_count: int = 0
    is_store_warehouse: int = 0
    mapped_store_name: str = ""

    @classmethod
    def from_query_row(cls, row: Mapping[str, Any]) -> "InventoryWarehouseSummary":
        return cls(
            rank=_as_int(row.get("rank")),
            warehouse_code=str(row.get("warehouse_code", "") or ""),
            warehouse_name=str(row.get("warehouse_name", "") or ""),
            warehouse_type=str(row.get("warehouse_type", "") or ""),
            inventory_amount=_as_float(row.get("inventory_amount")),
            inventory_qty=_as_float(row.get("inventory_qty")),
            sku_count=_as_int(row.get("sku_count")),
            is_store_warehouse=_as_int(row.get("is_store_warehouse")),
            mapped_store_name=str(row.get("mapped_store_name", "") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class InventoryStoreSummary:
    rank: int
    store_name: str
    inventory_amount: float = 0.0
    inventory_qty: float = 0.0
    sku_count: int = 0

    @classmethod
    def from_query_row(cls, row: Mapping[str, Any]) -> "InventoryStoreSummary":
        return cls(
            rank=_as_int(row.get("rank")),
            store_name=str(row.get("store_name", "") or ""),
            inventory_amount=_as_float(row.get("inventory_amount")),
            inventory_qty=_as_float(row.get("inventory_qty")),
            sku_count=_as_int(row.get("sku_count")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class InventoryRegionSummary:
    region_name: str
    inventory_amount: float = 0.0
    inventory_qty: float = 0.0
    contribution_rate: float = 0.0

    @classmethod
    def from_query_row(cls, row: Mapping[str, Any]) -> "InventoryRegionSummary":
        return cls(
            region_name=str(row.get("region_name", "") or "未分区"),
            inventory_amount=_as_float(row.get("inventory_amount")),
            inventory_qty=_as_float(row.get("inventory_qty")),
            contribution_rate=_as_float(row.get("contribution_rate")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class InventoryCategorySummary:
    category_name: str
    inventory_amount: float = 0.0
    inventory_qty: float = 0.0
    contribution_rate: float = 0.0

    @classmethod
    def from_query_row(cls, row: Mapping[str, Any]) -> "InventoryCategorySummary":
        return cls(
            category_name=str(row.get("category_name", "") or "未分类"),
            inventory_amount=_as_float(row.get("inventory_amount")),
            inventory_qty=_as_float(row.get("inventory_qty")),
            contribution_rate=_as_float(row.get("contribution_rate")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class InventoryWaveSummary:
    wave_name: str
    inventory_amount: float = 0.0
    inventory_qty: float = 0.0
    contribution_rate: float = 0.0

    @classmethod
    def from_query_row(cls, row: Mapping[str, Any]) -> "InventoryWaveSummary":
        return cls(
            wave_name=str(row.get("wave_name", "") or "未识别"),
            inventory_amount=_as_float(row.get("inventory_amount")),
            inventory_qty=_as_float(row.get("inventory_qty")),
            contribution_rate=_as_float(row.get("contribution_rate")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class InventoryHealthSummary:
    health_key: str
    health_name: str
    color_class: str
    sku_count: int = 0
    inventory_qty: float = 0.0
    inventory_amount: float = 0.0

    @classmethod
    def from_query_row(cls, row: Mapping[str, Any]) -> "InventoryHealthSummary":
        return cls(
            health_key=str(row.get("health_key", "") or ""),
            health_name=str(row.get("health_name", "") or ""),
            color_class=str(row.get("color_class", "") or "secondary"),
            sku_count=_as_int(row.get("sku_count")),
            inventory_qty=_as_float(row.get("inventory_qty")),
            inventory_amount=_as_float(row.get("inventory_amount")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class InventoryChannelOption:
    channel_code: str
    channel_name: str
    store_count: int = 0
    inventory_qty: float = 0.0
    inventory_amount: float = 0.0

    @classmethod
    def from_query_row(cls, row: Mapping[str, Any]) -> "InventoryChannelOption":
        return cls(
            channel_code=str(row.get("channel_code", "") or ""),
            channel_name=str(row.get("channel_name", "") or ""),
            store_count=_as_int(row.get("store_count")),
            inventory_qty=_as_float(row.get("inventory_qty")),
            inventory_amount=_as_float(row.get("inventory_amount")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class InventoryStoreOption:
    store_code: str
    store_name: str
    warehouse_code: str
    inventory_qty: float = 0.0
    inventory_amount: float = 0.0

    @classmethod
    def from_query_row(cls, row: Mapping[str, Any]) -> "InventoryStoreOption":
        return cls(
            store_code=str(row.get("store_code", "") or ""),
            store_name=str(row.get("store_name", "") or ""),
            warehouse_code=str(row.get("warehouse_code", "") or ""),
            inventory_qty=_as_float(row.get("inventory_qty")),
            inventory_amount=_as_float(row.get("inventory_amount")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class InventoryAnalysisContext:
    period: InventoryPeriod
    kpis: InventoryKPI
    top_products: list[InventoryTopProduct] = field(default_factory=list)
    warehouse_ranking: list[InventoryWarehouseSummary] = field(default_factory=list)
    store_ranking: list[InventoryStoreSummary] = field(default_factory=list)
    region_summary: list[InventoryRegionSummary] = field(default_factory=list)
    category_summary: list[InventoryCategorySummary] = field(default_factory=list)
    health_summary: list[InventoryHealthSummary] = field(default_factory=list)
    selected_scope: str = "women"
    selected_channel_code: str = ""
    selected_channel_name: str = ""
    selected_store_code: str = ""
    selected_store_name: str = ""
    channel_options: list[InventoryChannelOption] = field(default_factory=list)
    store_options: list[InventoryStoreOption] = field(default_factory=list)
    data_quality_note: str = "库存数据来源于 ERP 库存快照。部分渠道或门店未完整执行出入库流程，数据可能与实际库存存在偏差，请结合业务实际判断。"
    filter_warning: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "period": self.period.to_dict(),
            "kpis": self.kpis.to_dict(),
            "top_products": [item.to_dict() for item in self.top_products],
            "warehouse_ranking": [item.to_dict() for item in self.warehouse_ranking],
            "store_ranking": [item.to_dict() for item in self.store_ranking],
            "region_summary": [item.to_dict() for item in self.region_summary],
            "category_summary": [item.to_dict() for item in self.category_summary],
            "health_summary": [item.to_dict() for item in self.health_summary],
            "selected_scope": self.selected_scope,
            "selected_channel_code": self.selected_channel_code,
            "selected_channel_name": self.selected_channel_name,
            "selected_store_code": self.selected_store_code,
            "selected_store_name": self.selected_store_name,
            "channel_options": [item.to_dict() for item in self.channel_options],
            "store_options": [item.to_dict() for item in self.store_options],
            "data_quality_note": self.data_quality_note,
            "filter_warning": self.filter_warning,
        }