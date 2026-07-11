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

    @classmethod
    def from_query_row(cls, row: Mapping[str, Any]) -> "InventoryKPI":
        return cls(
            current_inventory_amount=_as_float(row.get("current_inventory_amount")),
            current_inventory_qty=_as_float(row.get("current_inventory_qty")),
            inventory_sku_count=_as_int(row.get("inventory_sku_count")),
            warehouse_count=_as_int(row.get("warehouse_count")),
            store_warehouse_count=_as_int(row.get("store_warehouse_count")),
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
class InventoryAnalysisContext:
    period: InventoryPeriod
    kpis: InventoryKPI
    top_products: list[InventoryTopProduct] = field(default_factory=list)
    warehouse_ranking: list[InventoryWarehouseSummary] = field(default_factory=list)
    store_ranking: list[InventoryStoreSummary] = field(default_factory=list)
    region_summary: list[InventoryRegionSummary] = field(default_factory=list)
    category_summary: list[InventoryCategorySummary] = field(default_factory=list)
    wave_summary: list[InventoryWaveSummary] = field(default_factory=list)
    selected_scope: str = "women"

    def to_dict(self) -> dict[str, Any]:
        return {
            "period": self.period.to_dict(),
            "kpis": self.kpis.to_dict(),
            "top_products": [item.to_dict() for item in self.top_products],
            "warehouse_ranking": [item.to_dict() for item in self.warehouse_ranking],
            "store_ranking": [item.to_dict() for item in self.store_ranking],
            "region_summary": [item.to_dict() for item in self.region_summary],
            "category_summary": [item.to_dict() for item in self.category_summary],
            "wave_summary": [item.to_dict() for item in self.wave_summary],
            "selected_scope": self.selected_scope,
        }