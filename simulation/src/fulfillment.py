"""Fulfillment simulation logic for FAIA."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from simulation.src.state import FulfillmentRecord, SimulationContext, SimulationState


@dataclass(frozen=True)
class DemandRecord:
    """Demand for one FDC-SKU-day cell."""

    simulation_date: str
    fdc_id: str
    sku_id: str
    demand_qty: int
    order_count: int = 0


def load_demand_for_date(path: Path, simulation_date: str) -> list[DemandRecord]:
    """Load FDC-SKU demand rows for one simulation date."""

    rows: list[DemandRecord] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row["date"] != simulation_date:
                continue
            rows.append(
                DemandRecord(
                    simulation_date=row["date"],
                    fdc_id=row["fdc_id"],
                    sku_id=row["sku_id"],
                    demand_qty=int(row["demand_qty"]),
                    order_count=int(row["order_count"]),
                )
            )
    return rows


def fulfill_demand_record(
    demand: DemandRecord,
    state: SimulationState,
    context: SimulationContext,
) -> FulfillmentRecord:
    """Fulfill a single demand cell through FDC local, RDC fallback, and lost sales."""

    if demand.demand_qty < 0:
        raise ValueError("demand_qty must be non-negative")
    if demand.fdc_id not in context.fdc_to_rdc:
        raise ValueError(f"Unknown FDC in demand: {demand.fdc_id}")

    rdc_id = context.fdc_to_rdc[demand.fdc_id]
    local_allowed = (demand.fdc_id, demand.sku_id) in context.eligible_pairs
    fdc_fulfilled_qty = 0
    if local_allowed:
        fdc_fulfilled_qty = state.consume_fdc_inventory(
            demand.fdc_id,
            demand.sku_id,
            demand.demand_qty,
        )

    unmet_after_fdc = demand.demand_qty - fdc_fulfilled_qty
    rdc_fallback_qty = state.consume_rdc_inventory(rdc_id, demand.sku_id, unmet_after_fdc)
    lost_sales_qty = unmet_after_fdc - rdc_fallback_qty

    record = FulfillmentRecord(
        simulation_date=demand.simulation_date,
        fdc_id=demand.fdc_id,
        rdc_id=rdc_id,
        sku_id=demand.sku_id,
        demand_qty=demand.demand_qty,
        fdc_fulfilled_qty=fdc_fulfilled_qty,
        rdc_fallback_qty=rdc_fallback_qty,
        lost_sales_qty=lost_sales_qty,
    )
    state.record_fulfillment(record)
    return record


def fulfill_demands_for_date(
    simulation_date: str,
    demand_records: Iterable[DemandRecord],
    state: SimulationState,
    context: SimulationContext,
) -> list[FulfillmentRecord]:
    """Fulfill all demand records for one simulation date."""

    state.current_date = simulation_date
    results: list[FulfillmentRecord] = []
    for demand in demand_records:
        if demand.simulation_date != simulation_date:
            raise ValueError(
                f"demand date mismatch: expected {simulation_date}, got {demand.simulation_date}"
            )
        results.append(fulfill_demand_record(demand, state, context))
    state.validate_non_negative()
    validate_fulfillment_records(results)
    return results


def fulfillment_result_row(
    record: FulfillmentRecord,
    context: SimulationContext,
) -> dict[str, object]:
    """Convert a fulfillment record to output schema row."""

    return {
        "experiment_id": context.experiment_id,
        "data_version": context.data_version,
        "policy_version": context.policy_version,
        "simulation_rule_version": context.simulation_rule_version,
        "simulation_date": record.simulation_date,
        "fdc_id": record.fdc_id,
        "rdc_id": record.rdc_id,
        "sku_id": record.sku_id,
        "demand_qty": record.demand_qty,
        "fdc_fulfilled_qty": record.fdc_fulfilled_qty,
        "rdc_fallback_qty": record.rdc_fallback_qty,
        "lost_sales_qty": record.lost_sales_qty,
    }


def fulfillment_totals(records: Iterable[FulfillmentRecord]) -> dict[str, int]:
    """Aggregate fulfillment records into total quantities."""

    totals = {
        "demand_qty": 0,
        "fdc_fulfilled_qty": 0,
        "rdc_fallback_qty": 0,
        "lost_sales_qty": 0,
    }
    for record in records:
        totals["demand_qty"] += record.demand_qty
        totals["fdc_fulfilled_qty"] += record.fdc_fulfilled_qty
        totals["rdc_fallback_qty"] += record.rdc_fallback_qty
        totals["lost_sales_qty"] += record.lost_sales_qty
    return totals


def validate_fulfillment_records(records: Iterable[FulfillmentRecord]) -> None:
    """Validate demand conservation and non-negative fulfillment quantities."""

    errors = 0
    for record in records:
        values = [
            record.demand_qty,
            record.fdc_fulfilled_qty,
            record.rdc_fallback_qty,
            record.lost_sales_qty,
        ]
        if min(values) < 0:
            errors += 1
            continue
        if record.demand_qty != record.fdc_fulfilled_qty + record.rdc_fallback_qty + record.lost_sales_qty:
            errors += 1
    if errors:
        raise ValueError(f"fulfillment validation failed for {errors} records")

