"""Metric aggregation for FAIA simulation."""

from __future__ import annotations

from typing import Iterable

from simulation.src.cost import CostRecord, cost_totals
from simulation.src.fulfillment import fulfillment_totals
from simulation.src.state import FulfillmentRecord, SimulationContext


def safe_ratio(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def build_metrics_summary(
    context: SimulationContext,
    fulfillment_records: Iterable[FulfillmentRecord],
    cost_records: Iterable[CostRecord],
    simulation_start_date: str | None = None,
    simulation_end_date: str | None = None,
) -> dict[str, object]:
    fulfillment = fulfillment_totals(fulfillment_records)
    costs = cost_totals(cost_records)
    total_demand = fulfillment["demand_qty"]
    fdc_fulfilled = fulfillment["fdc_fulfilled_qty"]
    rdc_fallback = fulfillment["rdc_fallback_qty"]
    lost_sales = fulfillment["lost_sales_qty"]
    summary = {
        "experiment_id": context.experiment_id,
        "data_version": context.data_version,
        "assortment_version": context.assortment_version,
        "policy_version": context.policy_version,
        "simulation_rule_version": context.simulation_rule_version,
        "simulation_start_date": simulation_start_date or context.simulation_start_date,
        "simulation_end_date": simulation_end_date or context.simulation_end_date,
        "total_demand_qty": total_demand,
        "fdc_fulfilled_qty": fdc_fulfilled,
        "rdc_fallback_qty": rdc_fallback,
        "lost_sales_qty": lost_sales,
        "fdc_fulfillment_rate": round(safe_ratio(fdc_fulfilled, total_demand), 8),
        "loss_ratio": round(safe_ratio(lost_sales, total_demand), 8),
        "transfer_cost": costs["transfer_cost"],
        "rdc_fallback_cost": costs["rdc_fallback_cost"],
        "lost_sales_cost": costs["lost_sales_cost"],
        "holding_cost": costs["holding_cost"],
        "total_cost": costs["total_cost"],
    }
    validate_metrics_summary(summary)
    return summary


def validate_metrics_summary(summary: dict[str, object]) -> None:
    total_demand = int(summary["total_demand_qty"])
    fdc_fulfilled = int(summary["fdc_fulfilled_qty"])
    rdc_fallback = int(summary["rdc_fallback_qty"])
    lost_sales = int(summary["lost_sales_qty"])
    if total_demand != fdc_fulfilled + rdc_fallback + lost_sales:
        raise ValueError("metrics summary violates demand conservation")
    for field in ["fdc_fulfillment_rate", "loss_ratio"]:
        value = float(summary[field])
        if value < 0 or value > 1:
            raise ValueError(f"{field} must be between 0 and 1")
    total_cost = float(summary["total_cost"])
    expected_cost = (
        float(summary["transfer_cost"])
        + float(summary["rdc_fallback_cost"])
        + float(summary["lost_sales_cost"])
        + float(summary["holding_cost"])
    )
    if abs(total_cost - expected_cost) > 1e-6:
        raise ValueError("metrics summary violates cost conservation")
