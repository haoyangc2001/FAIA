"""Cost computation for FAIA simulation."""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from simulation.src.allocation import TransferAllocationResult
from simulation.src.state import FulfillmentRecord, SimulationContext


@dataclass(frozen=True)
class CostRates:
    transfer_cost: float
    rdc_fallback_cost: float
    lost_sales_cost: float
    holding_cost: float


@dataclass(frozen=True)
class CostRecord:
    simulation_date: str
    cost_scope: str
    scope_id: str
    sku_id: str
    transfer_cost: float
    rdc_fallback_cost: float
    lost_sales_cost: float
    holding_cost: float

    @property
    def total_cost(self) -> float:
        return self.transfer_cost + self.rdc_fallback_cost + self.lost_sales_cost + self.holding_cost


def load_cost_rates(path: Path) -> CostRates:
    values: dict[str, float] = {}
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            values[row["cost_item"]] = float(row["value"])
    required = {"transfer_cost", "rdc_fallback_cost", "lost_sales_cost", "holding_cost"}
    missing = sorted(required - set(values))
    if missing:
        raise ValueError(f"cost_config missing cost items: {missing}")
    return CostRates(
        transfer_cost=values["transfer_cost"],
        rdc_fallback_cost=values["rdc_fallback_cost"],
        lost_sales_cost=values["lost_sales_cost"],
        holding_cost=values["holding_cost"],
    )


def build_cost_records(
    simulation_date: str,
    fulfillment_records: Iterable[FulfillmentRecord],
    transfer_results: Iterable[TransferAllocationResult],
    daily_state_rows: Iterable[dict[str, object]],
    rates: CostRates,
) -> list[CostRecord]:
    """Build scoped daily cost records from simulation outputs."""

    costs: dict[tuple[str, str, str], dict[str, float]] = defaultdict(
        lambda: {
            "transfer_cost": 0.0,
            "rdc_fallback_cost": 0.0,
            "lost_sales_cost": 0.0,
            "holding_cost": 0.0,
        }
    )

    for transfer in transfer_results:
        if transfer.actual_transfer_qty <= 0:
            continue
        key = ("fdc", transfer.fdc_id, transfer.sku_id)
        costs[key]["transfer_cost"] += transfer.actual_transfer_qty * rates.transfer_cost

    for record in fulfillment_records:
        key = ("fdc", record.fdc_id, record.sku_id)
        costs[key]["rdc_fallback_cost"] += record.rdc_fallback_qty * rates.rdc_fallback_cost
        costs[key]["lost_sales_cost"] += record.lost_sales_qty * rates.lost_sales_cost

    for row in daily_state_rows:
        node_type = str(row["node_type"])
        node_id = str(row["node_id"])
        sku_id = str(row["sku_id"])
        scope = "fdc" if node_type == "FDC" else "rdc"
        on_hand_qty = int(row["on_hand_qty"])
        costs[(scope, node_id, sku_id)]["holding_cost"] += on_hand_qty * rates.holding_cost

    records = [
        CostRecord(
            simulation_date=simulation_date,
            cost_scope=scope,
            scope_id=scope_id,
            sku_id=sku_id,
            transfer_cost=round(values["transfer_cost"], 6),
            rdc_fallback_cost=round(values["rdc_fallback_cost"], 6),
            lost_sales_cost=round(values["lost_sales_cost"], 6),
            holding_cost=round(values["holding_cost"], 6),
        )
        for (scope, scope_id, sku_id), values in sorted(costs.items())
        if any(value > 0 for value in values.values())
    ]
    global_values = {
        "transfer_cost": sum(record.transfer_cost for record in records),
        "rdc_fallback_cost": sum(record.rdc_fallback_cost for record in records),
        "lost_sales_cost": sum(record.lost_sales_cost for record in records),
        "holding_cost": sum(record.holding_cost for record in records),
    }
    records.append(
        CostRecord(
            simulation_date=simulation_date,
            cost_scope="global",
            scope_id="ALL",
            sku_id="ALL",
            transfer_cost=round(global_values["transfer_cost"], 6),
            rdc_fallback_cost=round(global_values["rdc_fallback_cost"], 6),
            lost_sales_cost=round(global_values["lost_sales_cost"], 6),
            holding_cost=round(global_values["holding_cost"], 6),
        )
    )
    validate_cost_records(records)
    return records


def cost_result_row(record: CostRecord, context: SimulationContext) -> dict[str, object]:
    return {
        "experiment_id": context.experiment_id,
        "data_version": context.data_version,
        "policy_version": context.policy_version,
        "simulation_rule_version": context.simulation_rule_version,
        "simulation_date": record.simulation_date,
        "cost_scope": record.cost_scope,
        "scope_id": record.scope_id,
        "sku_id": record.sku_id,
        "transfer_cost": round(record.transfer_cost, 6),
        "rdc_fallback_cost": round(record.rdc_fallback_cost, 6),
        "lost_sales_cost": round(record.lost_sales_cost, 6),
        "holding_cost": round(record.holding_cost, 6),
        "total_cost": round(record.total_cost, 6),
    }


def cost_totals(records: Iterable[CostRecord]) -> dict[str, float]:
    global_rows = [record for record in records if record.cost_scope == "global"]
    if global_rows:
        transfer_cost = sum(record.transfer_cost for record in global_rows)
        rdc_fallback_cost = sum(record.rdc_fallback_cost for record in global_rows)
        lost_sales_cost = sum(record.lost_sales_cost for record in global_rows)
        holding_cost = sum(record.holding_cost for record in global_rows)
        return {
            "transfer_cost": round(transfer_cost, 6),
            "rdc_fallback_cost": round(rdc_fallback_cost, 6),
            "lost_sales_cost": round(lost_sales_cost, 6),
            "holding_cost": round(holding_cost, 6),
            "total_cost": round(transfer_cost + rdc_fallback_cost + lost_sales_cost + holding_cost, 6),
        }
    transfer_cost = 0.0
    rdc_fallback_cost = 0.0
    lost_sales_cost = 0.0
    holding_cost = 0.0
    for record in records:
        transfer_cost += record.transfer_cost
        rdc_fallback_cost += record.rdc_fallback_cost
        lost_sales_cost += record.lost_sales_cost
        holding_cost += record.holding_cost
    return {
        "transfer_cost": round(transfer_cost, 6),
        "rdc_fallback_cost": round(rdc_fallback_cost, 6),
        "lost_sales_cost": round(lost_sales_cost, 6),
        "holding_cost": round(holding_cost, 6),
        "total_cost": round(transfer_cost + rdc_fallback_cost + lost_sales_cost + holding_cost, 6),
    }


def validate_cost_records(records: Iterable[CostRecord]) -> None:
    errors = 0
    for record in records:
        values = [
            record.transfer_cost,
            record.rdc_fallback_cost,
            record.lost_sales_cost,
            record.holding_cost,
            record.total_cost,
        ]
        if min(values) < 0:
            errors += 1
        expected_total = record.transfer_cost + record.rdc_fallback_cost + record.lost_sales_cost + record.holding_cost
        if abs(record.total_cost - expected_total) > 1e-6:
            errors += 1
    if errors:
        raise ValueError(f"cost validation failed for {errors} records")
