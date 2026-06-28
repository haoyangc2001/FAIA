"""Evaluate inventory transfer recommendations with the simulation primitives."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Any

from inventory.src.common import (
    input_path,
    int_value,
    iter_csv_rows,
    read_yaml,
    write_csv,
    write_json,
)
from inventory.src.state_builder import load_assortment_pairs, load_warehouse_context
from simulation.src.allocation import (
    allocate_transfer_decision,
    apply_arrivals,
    apply_transfer_allocation,
    calculate_arrival_date,
    parse_date,
    rules_from_config,
    validate_transfer_event,
)
from simulation.src.cost import build_cost_records, cost_result_row, load_cost_rates
from simulation.src.engine import (
    COST_RESULT_FIELDS,
    DAILY_STATE_FIELDS,
    FULFILLMENT_RESULT_FIELDS,
    TRANSFER_RESULT_FIELDS,
    date_range,
)
from simulation.src.fulfillment import DemandRecord, fulfillment_result_row, fulfillment_totals, fulfill_demands_for_date
from simulation.src.metrics import build_metrics_summary
from simulation.src.policy import TransferDecision
from simulation.src.state import SimulationContext, SimulationState, TransferEvent


def load_initial_inventory_rows(path: Path, initial_inventory_date: str) -> list[dict[str, str]]:
    rows = [row for row in iter_csv_rows(path) if row["date"] == initial_inventory_date]
    if not rows:
        raise ValueError(f"no inventory rows found for initial_inventory_date={initial_inventory_date}")
    return rows


def load_open_pipeline_events(path: Path, initial_inventory_date: str) -> list[TransferEvent]:
    initial_dt = parse_date(initial_inventory_date)
    events: list[TransferEvent] = []
    for row in iter_csv_rows(path):
        ship_dt = parse_date(row["ship_date"])
        arrival_dt = parse_date(row["arrival_date"])
        if ship_dt <= initial_dt < arrival_dt:
            event = TransferEvent(
                ship_date=row["ship_date"],
                arrival_date=row["arrival_date"],
                rdc_id=row["rdc_id"],
                fdc_id=row["fdc_id"],
                sku_id=row["sku_id"],
                qty=int_value(row["transfer_qty"]),
                lead_time_days=int_value(row["lead_time_days"]),
            )
            validate_transfer_event(event)
            events.append(event)
    return events


def load_demands_by_date(path: Path, dates: set[str]) -> dict[str, list[DemandRecord]]:
    demands = {date: [] for date in dates}
    for row in iter_csv_rows(path):
        date = row["date"]
        if date not in demands:
            continue
        demands[date].append(
            DemandRecord(
                simulation_date=date,
                fdc_id=row["fdc_id"],
                sku_id=row["sku_id"],
                demand_qty=int_value(row["demand_qty"]),
                order_count=int_value(row.get("order_count", 0)),
            )
        )
    return demands


def load_transfer_recommendations(path: Path) -> dict[str, list[dict[str, str]]]:
    by_ship_date: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in iter_csv_rows(path):
        qty = transfer_qty_for_simulation(row)
        if qty <= 0:
            continue
        by_ship_date[row["ship_date"]].append(row)
    return dict(by_ship_date)


def transfer_qty_for_simulation(row: dict[str, str]) -> int:
    if row.get("actual_transfer_qty") not in (None, ""):
        return int_value(row["actual_transfer_qty"])
    return int_value(row["recommended_transfer_qty"])


def build_context(config: dict[str, Any]) -> SimulationContext:
    warehouse = load_warehouse_context(input_path(config, "warehouse_master"))
    selected_pairs = load_assortment_pairs(
        input_path(config, "assortment_result"),
        str(config["assortment_version"]),
        str(config["decision_date"]),
    )
    return SimulationContext(
        experiment_id=str(config["experiment_id"]),
        data_version=str(config["data_version"]),
        assortment_version=str(config["assortment_version"]),
        policy_version=str(config["policy"]["policy_version"]),
        simulation_rule_version=str(config["simulation_rule_version"]),
        simulation_start_date=str(config["effective_start_date"]),
        simulation_end_date=str(config["effective_end_date"]),
        fdc_to_rdc=warehouse.fdc_to_rdc,
        fdc_capacity=warehouse.fdc_capacity,
        eligible_pairs=set(selected_pairs),
    )


def decision_from_recommendation(row: dict[str, str], context: SimulationContext) -> TransferDecision:
    qty = transfer_qty_for_simulation(row)
    return TransferDecision(
        simulation_date=row["ship_date"],
        rdc_id=row["rdc_id"],
        fdc_id=row["fdc_id"],
        sku_id=row["sku_id"],
        recommended_transfer_qty=qty,
        policy_version=context.policy_version,
        target_inventory_qty=int_value(row.get("target_inventory_qty", 0)),
        safety_stock_qty=int_value(row.get("safety_stock_qty", 0)),
        lead_time_days=int_value(row.get("lead_time_days", 0)),
        reason=row.get("reason", ""),
    )


def run_inventory_simulation(
    config: dict[str, Any],
    transfer_recommendation_path: Path,
) -> dict[str, Any]:
    """Replay inventory recommendations through simulation primitives."""

    context = build_context(config)
    run_dir = Path(str(config["output"]["run_dir"]))
    rules = read_yaml(Path(str(config["rules"]["simulation_rule"])))
    allocation_rules = rules_from_config(rules)
    initial_inventory_date = str(config["initial_inventory_date"])
    initial_rows = load_initial_inventory_rows(input_path(config, "inventory_daily_state"), initial_inventory_date)
    state = SimulationState.from_inventory_rows(initial_inventory_date, initial_rows)
    for event in load_open_pipeline_events(input_path(config, "transfer_plan"), initial_inventory_date):
        state.add_pipeline_transfer(event)
    state.validate_non_negative()

    simulation_dates = date_range(str(config["effective_start_date"]), str(config["effective_end_date"]))
    demands_by_date = load_demands_by_date(input_path(config, "fdc_sku_daily_demand"), set(simulation_dates))
    recommendations_by_date = load_transfer_recommendations(transfer_recommendation_path)
    cost_rates = load_cost_rates(input_path(config, "cost_config"))

    daily_state_path = run_dir / "simulation_daily_state.csv"
    transfer_result_path = run_dir / "simulation_transfer_result.csv"
    fulfillment_result_path = run_dir / "simulation_fulfillment_result.csv"
    cost_result_path = run_dir / "simulation_cost_result.csv"
    metrics_summary_path = run_dir / "simulation_metrics.json"
    daily_log_path = run_dir / "simulation_daily_log.json"

    all_fulfillment_records = []
    all_cost_records = []
    daily_logs: list[dict[str, Any]] = []
    row_counts = {
        "simulation_daily_state": 0,
        "simulation_transfer_result": 0,
        "simulation_fulfillment_result": 0,
        "simulation_cost_result": 0,
    }

    with daily_state_path.open("w", encoding="utf-8", newline="") as daily_state_file, transfer_result_path.open(
        "w", encoding="utf-8", newline=""
    ) as transfer_file, fulfillment_result_path.open("w", encoding="utf-8", newline="") as fulfillment_file, cost_result_path.open(
        "w", encoding="utf-8", newline=""
    ) as cost_file:
        daily_state_writer = csv.DictWriter(daily_state_file, fieldnames=DAILY_STATE_FIELDS)
        transfer_writer = csv.DictWriter(transfer_file, fieldnames=TRANSFER_RESULT_FIELDS)
        fulfillment_writer = csv.DictWriter(fulfillment_file, fieldnames=FULFILLMENT_RESULT_FIELDS)
        cost_writer = csv.DictWriter(cost_file, fieldnames=COST_RESULT_FIELDS)
        daily_state_writer.writeheader()
        transfer_writer.writeheader()
        fulfillment_writer.writeheader()
        cost_writer.writeheader()

        for simulation_date in simulation_dates:
            state.clear_daily_events()
            state.current_date = simulation_date

            arrivals = apply_arrivals(state, simulation_date)
            transfer_results = []
            for row in recommendations_by_date.get(simulation_date, []):
                decision = decision_from_recommendation(row, context)
                result = allocate_transfer_decision(
                    decision=decision,
                    state=state,
                    context=context,
                    rules=allocation_rules,
                    transfer_id=row["transfer_id"],
                )
                if result.actual_transfer_qty > 0:
                    apply_transfer_allocation(state, result)
                transfer_writer.writerow(result.to_result_row(context))
                row_counts["simulation_transfer_result"] += 1
                transfer_results.append(result)

            fulfillment_records = fulfill_demands_for_date(
                simulation_date=simulation_date,
                demand_records=demands_by_date.get(simulation_date, []),
                state=state,
                context=context,
            )
            for record in fulfillment_records:
                fulfillment_writer.writerow(fulfillment_result_row(record, context))
                row_counts["simulation_fulfillment_result"] += 1

            daily_state_rows = state.daily_state_rows(context)
            for row in daily_state_rows:
                daily_state_writer.writerow(row)
                row_counts["simulation_daily_state"] += 1

            cost_records = build_cost_records(
                simulation_date=simulation_date,
                fulfillment_records=fulfillment_records,
                transfer_results=transfer_results,
                daily_state_rows=daily_state_rows,
                rates=cost_rates,
            )
            for record in cost_records:
                cost_writer.writerow(cost_result_row(record, context))
                row_counts["simulation_cost_result"] += 1

            fulfillment_totals_day = fulfillment_totals(fulfillment_records)
            daily_logs.append(
                {
                    "simulation_date": simulation_date,
                    "arrival_events": len(arrivals),
                    "arrival_qty": sum(event.qty for event in arrivals),
                    "policy_decisions": len(transfer_results),
                    "recommended_transfer_qty": sum(result.recommended_transfer_qty for result in transfer_results),
                    "actual_transfer_qty": sum(result.actual_transfer_qty for result in transfer_results),
                    "demand_cells": len(fulfillment_records),
                    **fulfillment_totals_day,
                }
            )
            all_fulfillment_records.extend(fulfillment_records)
            all_cost_records.extend(cost_records)

    metrics_summary = build_metrics_summary(
        context=context,
        fulfillment_records=all_fulfillment_records,
        cost_records=all_cost_records,
        simulation_start_date=str(config["effective_start_date"]),
        simulation_end_date=str(config["effective_end_date"]),
    )
    write_json(metrics_summary_path, metrics_summary)
    write_json(daily_log_path, {"daily_logs": daily_logs})
    return {
        "metrics_summary": metrics_summary,
        "row_counts": row_counts,
        "outputs": {
            "simulation_daily_state": daily_state_path,
            "simulation_transfer_result": transfer_result_path,
            "simulation_fulfillment_result": fulfillment_result_path,
            "simulation_cost_result": cost_result_path,
            "simulation_metrics": metrics_summary_path,
            "simulation_daily_log": daily_log_path,
        },
    }


def simulation_transfer_recommendation_rows(path: Path) -> list[dict[str, str]]:
    return list(iter_csv_rows(path))
