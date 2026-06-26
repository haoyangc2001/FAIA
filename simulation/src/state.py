"""Core state structures for the FAIA business simulator."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Iterable


InventoryKey = tuple[str, str]
PipelineKey = tuple[str, str, str, str, int]
TransferKey = tuple[str, str, str]
FulfillmentKey = tuple[str, str, str]


@dataclass(frozen=True)
class TransferEvent:
    """A transfer event that has entered the lead-time pipeline."""

    ship_date: str
    arrival_date: str
    rdc_id: str
    fdc_id: str
    sku_id: str
    qty: int
    lead_time_days: int


@dataclass(frozen=True)
class FulfillmentRecord:
    """Aggregated fulfillment result for one FDC-SKU-day demand cell."""

    simulation_date: str
    fdc_id: str
    rdc_id: str
    sku_id: str
    demand_qty: int
    fdc_fulfilled_qty: int
    rdc_fallback_qty: int
    lost_sales_qty: int


@dataclass
class SimulationContext:
    """Static identifiers and version fields for one simulation run."""

    experiment_id: str
    data_version: str
    assortment_version: str
    policy_version: str
    simulation_rule_version: str
    simulation_start_date: str
    simulation_end_date: str
    fdc_to_rdc: dict[str, str] = field(default_factory=dict)
    fdc_capacity: dict[str, int] = field(default_factory=dict)
    eligible_pairs: set[tuple[str, str]] = field(default_factory=set)


@dataclass
class SimulationState:
    """Mutable inventory and event state for daily simulation rollout."""

    current_date: str
    rdc_on_hand_inventory: Counter[InventoryKey] = field(default_factory=Counter)
    fdc_on_hand_inventory: Counter[InventoryKey] = field(default_factory=Counter)
    pipeline_inventory: dict[str, Counter[PipelineKey]] = field(default_factory=lambda: defaultdict(Counter))
    last_transfer_qty: Counter[TransferKey] = field(default_factory=Counter)
    last_fulfillment_result: list[FulfillmentRecord] = field(default_factory=list)
    lost_sales_state: Counter[FulfillmentKey] = field(default_factory=Counter)

    @classmethod
    def from_inventory_rows(cls, current_date: str, rows: Iterable[dict[str, str]]) -> "SimulationState":
        """Build initial state from inventory_daily_state style rows."""

        state = cls(current_date=current_date)
        for row in rows:
            node_type = row["node_type"]
            node_id = row["node_id"]
            sku_id = row["sku_id"]
            qty = int(row["on_hand_qty"])
            if node_type == "RDC":
                state.rdc_on_hand_inventory[(node_id, sku_id)] += qty
            elif node_type == "FDC":
                state.fdc_on_hand_inventory[(node_id, sku_id)] += qty
            else:
                raise ValueError(f"Unknown node_type: {node_type}")
        state.validate_non_negative()
        return state

    def get_rdc_on_hand(self, rdc_id: str, sku_id: str) -> int:
        return self.rdc_on_hand_inventory[(rdc_id, sku_id)]

    def get_fdc_on_hand(self, fdc_id: str, sku_id: str) -> int:
        return self.fdc_on_hand_inventory[(fdc_id, sku_id)]

    def get_fdc_in_transit(self, fdc_id: str, sku_id: str) -> int:
        return self._fdc_in_transit_counter()[(fdc_id, sku_id)]

    def get_fdc_inventory_position(self, fdc_id: str, sku_id: str) -> int:
        return self.get_fdc_on_hand(fdc_id, sku_id) + self.get_fdc_in_transit(fdc_id, sku_id)

    def fdc_has_sku_position(self, fdc_id: str, sku_id: str) -> bool:
        return self.get_fdc_inventory_position(fdc_id, sku_id) > 0

    def fdc_active_sku_count(self, fdc_id: str) -> int:
        sku_ids = {
            sku_id
            for node_id, sku_id in self.fdc_on_hand_inventory
            if node_id == fdc_id and self.fdc_on_hand_inventory[(node_id, sku_id)] > 0
        }
        for (node_id, sku_id), qty in self._fdc_in_transit_counter().items():
            if node_id == fdc_id and qty > 0:
                sku_ids.add(sku_id)
        return len(sku_ids)

    def add_rdc_inventory(self, rdc_id: str, sku_id: str, qty: int) -> None:
        self._ensure_non_negative_delta(qty)
        self.rdc_on_hand_inventory[(rdc_id, sku_id)] += qty

    def add_fdc_inventory(self, fdc_id: str, sku_id: str, qty: int) -> None:
        self._ensure_non_negative_delta(qty)
        self.fdc_on_hand_inventory[(fdc_id, sku_id)] += qty

    def consume_rdc_inventory(self, rdc_id: str, sku_id: str, qty: int) -> int:
        self._ensure_non_negative_delta(qty)
        key = (rdc_id, sku_id)
        consumed = min(self.rdc_on_hand_inventory[key], qty)
        if consumed > 0:
            self.rdc_on_hand_inventory[key] -= consumed
        return consumed

    def consume_fdc_inventory(self, fdc_id: str, sku_id: str, qty: int) -> int:
        self._ensure_non_negative_delta(qty)
        key = (fdc_id, sku_id)
        consumed = min(self.fdc_on_hand_inventory[key], qty)
        if consumed > 0:
            self.fdc_on_hand_inventory[key] -= consumed
        return consumed

    def add_pipeline_transfer(self, event: TransferEvent) -> None:
        if event.qty < 0:
            raise ValueError("pipeline transfer qty must be non-negative")
        key = (event.ship_date, event.rdc_id, event.fdc_id, event.sku_id, event.lead_time_days)
        self.pipeline_inventory[event.arrival_date][key] += event.qty
        self.last_transfer_qty[(event.rdc_id, event.fdc_id, event.sku_id)] += event.qty

    def pop_arrivals(self, simulation_date: str) -> list[TransferEvent]:
        arrivals = self.pipeline_inventory.pop(simulation_date, Counter())
        events: list[TransferEvent] = []
        for (ship_date, rdc_id, fdc_id, sku_id, lead_time_days), qty in arrivals.items():
            if qty <= 0:
                continue
            self.add_fdc_inventory(fdc_id, sku_id, qty)
            events.append(
                TransferEvent(
                    ship_date=ship_date,
                    arrival_date=simulation_date,
                    rdc_id=rdc_id,
                    fdc_id=fdc_id,
                    sku_id=sku_id,
                    qty=qty,
                    lead_time_days=lead_time_days,
                )
            )
        return events

    def record_fulfillment(self, record: FulfillmentRecord) -> None:
        if record.demand_qty != record.fdc_fulfilled_qty + record.rdc_fallback_qty + record.lost_sales_qty:
            raise ValueError("fulfillment record violates demand conservation")
        if min(record.demand_qty, record.fdc_fulfilled_qty, record.rdc_fallback_qty, record.lost_sales_qty) < 0:
            raise ValueError("fulfillment quantities must be non-negative")
        self.last_fulfillment_result.append(record)
        if record.lost_sales_qty:
            self.lost_sales_state[(record.simulation_date, record.fdc_id, record.sku_id)] += record.lost_sales_qty

    def clear_daily_events(self) -> None:
        self.last_transfer_qty.clear()
        self.last_fulfillment_result.clear()

    def validate_non_negative(self) -> None:
        for name, inventory in [
            ("rdc_on_hand_inventory", self.rdc_on_hand_inventory),
            ("fdc_on_hand_inventory", self.fdc_on_hand_inventory),
        ]:
            negatives = {key: qty for key, qty in inventory.items() if qty < 0}
            if negatives:
                raise ValueError(f"{name} contains negative inventory: {negatives}")
        for arrival_date, pipeline in self.pipeline_inventory.items():
            negatives = {key: qty for key, qty in pipeline.items() if qty < 0}
            if negatives:
                raise ValueError(f"pipeline_inventory contains negative qty for {arrival_date}: {negatives}")

    def daily_state_rows(self, context: SimulationContext) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for (rdc_id, sku_id), qty in sorted(self.rdc_on_hand_inventory.items()):
            rows.append(self._daily_state_row(context, rdc_id, "RDC", sku_id, qty, 0))
        fdc_in_transit = self._fdc_in_transit_counter()
        for (fdc_id, sku_id), qty in sorted(self.fdc_on_hand_inventory.items()):
            rows.append(self._daily_state_row(context, fdc_id, "FDC", sku_id, qty, fdc_in_transit[(fdc_id, sku_id)]))
        return rows

    def _daily_state_row(
        self,
        context: SimulationContext,
        node_id: str,
        node_type: str,
        sku_id: str,
        on_hand_qty: int,
        in_transit_qty: int,
    ) -> dict[str, object]:
        reserved_qty = 0
        available_qty = max(0, on_hand_qty - reserved_qty)
        return {
            "experiment_id": context.experiment_id,
            "data_version": context.data_version,
            "policy_version": context.policy_version,
            "simulation_rule_version": context.simulation_rule_version,
            "simulation_date": self.current_date,
            "node_id": node_id,
            "node_type": node_type,
            "sku_id": sku_id,
            "on_hand_qty": on_hand_qty,
            "reserved_qty": reserved_qty,
            "in_transit_qty": in_transit_qty,
            "available_qty": available_qty,
            "inventory_position_qty": available_qty + in_transit_qty,
        }

    def _fdc_in_transit_counter(self) -> Counter[InventoryKey]:
        in_transit: Counter[InventoryKey] = Counter()
        for pipeline in self.pipeline_inventory.values():
            for (_ship_date, _rdc_id, fdc_id, sku_id, _lead_time_days), qty in pipeline.items():
                in_transit[(fdc_id, sku_id)] += qty
        return in_transit

    @staticmethod
    def _ensure_non_negative_delta(qty: int) -> None:
        if qty < 0:
            raise ValueError("quantity delta must be non-negative")
