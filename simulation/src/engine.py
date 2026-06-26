"""Simulation engine that writes replayable run outputs."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

import yaml

from simulation.src.allocation import (
    allocate_transfer_decisions,
    apply_arrivals,
    apply_transfer_allocation,
    parse_date,
    rules_from_config,
)
from simulation.src.cost import build_cost_records, cost_result_row, cost_totals, load_cost_rates
from simulation.src.fulfillment import (
    DemandRecord,
    fulfillment_result_row,
    fulfillment_totals,
    fulfill_demands_for_date,
)
from simulation.src.initialization import initialize_simulation
from simulation.src.metrics import build_metrics_summary
from simulation.src.policy import load_policy
from simulation.src.state import FulfillmentRecord


DAILY_STATE_FIELDS = [
    "experiment_id",
    "data_version",
    "policy_version",
    "simulation_rule_version",
    "simulation_date",
    "node_id",
    "node_type",
    "sku_id",
    "on_hand_qty",
    "reserved_qty",
    "in_transit_qty",
    "available_qty",
    "inventory_position_qty",
]

TRANSFER_RESULT_FIELDS = [
    "experiment_id",
    "data_version",
    "policy_version",
    "simulation_rule_version",
    "simulation_date",
    "transfer_id",
    "rdc_id",
    "fdc_id",
    "sku_id",
    "recommended_transfer_qty",
    "actual_transfer_qty",
    "clipped_qty",
    "clip_reason",
    "ship_date",
    "arrival_date",
    "lead_time_days",
    "status",
]

FULFILLMENT_RESULT_FIELDS = [
    "experiment_id",
    "data_version",
    "policy_version",
    "simulation_rule_version",
    "simulation_date",
    "fdc_id",
    "rdc_id",
    "sku_id",
    "demand_qty",
    "fdc_fulfilled_qty",
    "rdc_fallback_qty",
    "lost_sales_qty",
]

COST_RESULT_FIELDS = [
    "experiment_id",
    "data_version",
    "policy_version",
    "simulation_rule_version",
    "simulation_date",
    "cost_scope",
    "scope_id",
    "sku_id",
    "transfer_cost",
    "rdc_fallback_cost",
    "lost_sales_cost",
    "holding_cost",
    "total_cost",
]


def date_range(start_date: str, end_date: str) -> list[str]:
    start = parse_date(start_date)
    end = parse_date(end_date)
    if end < start:
        raise ValueError(f"simulation_end_date {end_date} is earlier than start date {start_date}")
    days = []
    current = start
    while current <= end:
        days.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return days


def load_demands_by_date(path: Path, dates: set[str]) -> dict[str, list[DemandRecord]]:
    demands = {date: [] for date in dates}
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            date = row["date"]
            if date not in demands:
                continue
            demands[date].append(
                DemandRecord(
                    simulation_date=date,
                    fdc_id=row["fdc_id"],
                    sku_id=row["sku_id"],
                    demand_qty=int(row["demand_qty"]),
                    order_count=int(row["order_count"]),
                )
            )
    return demands


def write_json(path: Path, payload: dict[str, Any] | list[dict[str, Any]]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, sort_keys=False, allow_unicode=True)


def file_entry(path: Path, rows: int | None = None) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "path": str(path),
        "bytes": path.stat().st_size if path.exists() else 0,
    }
    if rows is not None:
        entry["rows"] = rows
    return entry


def run_simulation(config_path: Path) -> dict[str, Any]:
    init = initialize_simulation(config_path)
    context = init.context
    run_dir = Path(init.config["output"]["run_dir"])
    run_dir.mkdir(parents=True, exist_ok=True)
    report_dir = Path("simulation/reports")
    report_dir.mkdir(parents=True, exist_ok=True)

    policy = load_policy(Path(init.config["policy"]["path"]))
    if policy.policy_version != context.policy_version:
        raise ValueError(
            f"policy_version mismatch: config={context.policy_version}, policy={policy.policy_version}"
        )
    allocation_rules = rules_from_config(init.rules)
    cost_rates = load_cost_rates(init.input_paths.cost_config)
    simulation_dates = date_range(context.simulation_start_date, context.simulation_end_date)
    demands_by_date = load_demands_by_date(init.input_paths.fdc_sku_daily_demand, set(simulation_dates))

    daily_state_path = run_dir / "daily_state.csv"
    transfer_result_path = run_dir / "transfer_result.csv"
    fulfillment_result_path = run_dir / "fulfillment_result.csv"
    cost_result_path = run_dir / "cost_result.csv"
    metrics_summary_path = run_dir / "metrics_summary.json"
    daily_log_path = run_dir / "daily_log.json"
    simulation_manifest_path = run_dir / "simulation_manifest.yaml"
    config_snapshot_path = run_dir / "simulation_config.yaml"
    report_path = report_dir / f"{context.experiment_id}_simulation_report.md"

    all_fulfillment_records: list[FulfillmentRecord] = []
    all_cost_records = []
    daily_logs: list[dict[str, Any]] = []
    row_counts = {
        "daily_state": 0,
        "transfer_result": 0,
        "fulfillment_result": 0,
        "cost_result": 0,
    }

    with daily_state_path.open("w", encoding="utf-8", newline="") as daily_state_file, transfer_result_path.open(
        "w", encoding="utf-8", newline=""
    ) as transfer_file, fulfillment_result_path.open(
        "w", encoding="utf-8", newline=""
    ) as fulfillment_file, cost_result_path.open("w", encoding="utf-8", newline="") as cost_file:
        daily_state_writer = csv.DictWriter(daily_state_file, fieldnames=DAILY_STATE_FIELDS)
        transfer_writer = csv.DictWriter(transfer_file, fieldnames=TRANSFER_RESULT_FIELDS)
        fulfillment_writer = csv.DictWriter(fulfillment_file, fieldnames=FULFILLMENT_RESULT_FIELDS)
        cost_writer = csv.DictWriter(cost_file, fieldnames=COST_RESULT_FIELDS)
        daily_state_writer.writeheader()
        transfer_writer.writeheader()
        fulfillment_writer.writeheader()
        cost_writer.writeheader()

        for simulation_date in simulation_dates:
            init.state.clear_daily_events()
            init.state.current_date = simulation_date

            arrivals = apply_arrivals(init.state, simulation_date)
            decisions = policy.generate_decisions(
                simulation_date=simulation_date,
                state=init.state,
                context=context,
            )
            transfer_results = allocate_transfer_decisions(
                decisions=list(decisions),
                state=init.state,
                context=context,
                rules=allocation_rules,
                transfer_id_prefix=f"SIMT{simulation_date.replace('-', '')}",
            )
            for transfer in transfer_results:
                if transfer.actual_transfer_qty > 0:
                    apply_transfer_allocation(init.state, transfer)
                transfer_writer.writerow(transfer.to_result_row(context))
                row_counts["transfer_result"] += 1

            demand_records = demands_by_date.get(simulation_date, [])
            fulfillment_records = fulfill_demands_for_date(
                simulation_date=simulation_date,
                demand_records=demand_records,
                state=init.state,
                context=context,
            )
            for record in fulfillment_records:
                fulfillment_writer.writerow(fulfillment_result_row(record, context))
                row_counts["fulfillment_result"] += 1

            daily_state_rows = init.state.daily_state_rows(context)
            for row in daily_state_rows:
                daily_state_writer.writerow(row)
                row_counts["daily_state"] += 1

            cost_records = build_cost_records(
                simulation_date=simulation_date,
                fulfillment_records=fulfillment_records,
                transfer_results=transfer_results,
                daily_state_rows=daily_state_rows,
                rates=cost_rates,
            )
            for record in cost_records:
                cost_writer.writerow(cost_result_row(record, context))
                row_counts["cost_result"] += 1

            fulfillment_day_totals = fulfillment_totals(fulfillment_records)
            cost_day_totals = cost_totals(cost_records)
            daily_logs.append(
                {
                    "simulation_date": simulation_date,
                    "arrival_events": len(arrivals),
                    "arrival_qty": sum(event.qty for event in arrivals),
                    "policy_decisions": len(transfer_results),
                    "recommended_transfer_qty": sum(
                        transfer.recommended_transfer_qty for transfer in transfer_results
                    ),
                    "actual_transfer_qty": sum(transfer.actual_transfer_qty for transfer in transfer_results),
                    "demand_cells": len(demand_records),
                    **fulfillment_day_totals,
                    **cost_day_totals,
                }
            )
            all_fulfillment_records.extend(fulfillment_records)
            all_cost_records.extend(cost_records)

    metrics_summary = build_metrics_summary(
        context=context,
        fulfillment_records=all_fulfillment_records,
        cost_records=all_cost_records,
        simulation_start_date=context.simulation_start_date,
        simulation_end_date=context.simulation_end_date,
    )
    write_json(metrics_summary_path, metrics_summary)
    write_json(daily_log_path, daily_logs)
    write_yaml(config_snapshot_path, init.config)

    manifest = build_simulation_manifest(
        config_path=config_path,
        init=init,
        run_dir=run_dir,
        row_counts=row_counts,
        metrics_summary=metrics_summary,
        daily_log_count=len(daily_logs),
        output_paths={
            "daily_state": daily_state_path,
            "transfer_result": transfer_result_path,
            "fulfillment_result": fulfillment_result_path,
            "cost_result": cost_result_path,
            "metrics_summary": metrics_summary_path,
            "daily_log": daily_log_path,
            "simulation_config": config_snapshot_path,
            "report": report_path,
        },
    )
    write_report(report_path, manifest, metrics_summary, daily_logs)
    manifest["outputs"]["report"] = file_entry(report_path)
    write_stable_manifest(simulation_manifest_path, manifest)
    return manifest


def write_stable_manifest(path: Path, manifest: dict[str, Any]) -> None:
    """Write manifest while stabilizing the manifest's own file metadata."""

    for _ in range(5):
        previous_entry = manifest["outputs"].get("simulation_manifest")
        write_yaml(path, manifest)
        current_entry = file_entry(path)
        manifest["outputs"]["simulation_manifest"] = current_entry
        if previous_entry == current_entry:
            break
    write_yaml(path, manifest)


def build_simulation_manifest(
    config_path: Path,
    init,
    run_dir: Path,
    row_counts: dict[str, int],
    metrics_summary: dict[str, Any],
    daily_log_count: int,
    output_paths: dict[str, Path],
) -> dict[str, Any]:
    context = init.context
    outputs = {
        "daily_state": file_entry(output_paths["daily_state"], rows=row_counts["daily_state"]),
        "transfer_result": file_entry(output_paths["transfer_result"], rows=row_counts["transfer_result"]),
        "fulfillment_result": file_entry(output_paths["fulfillment_result"], rows=row_counts["fulfillment_result"]),
        "cost_result": file_entry(output_paths["cost_result"], rows=row_counts["cost_result"]),
        "metrics_summary": file_entry(output_paths["metrics_summary"]),
        "daily_log": file_entry(output_paths["daily_log"], rows=daily_log_count),
        "simulation_config": file_entry(output_paths["simulation_config"]),
    }
    return {
        "experiment_id": context.experiment_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "data_version": context.data_version,
        "assortment_version": context.assortment_version,
        "policy_version": context.policy_version,
        "simulation_rule_version": context.simulation_rule_version,
        "simulation_start_date": context.simulation_start_date,
        "simulation_end_date": context.simulation_end_date,
        "initial_inventory_date": init.config["initial_inventory_date"],
        "config": str(config_path),
        "run_dir": str(run_dir),
        "inputs": {
            "warehouse_master": str(init.input_paths.warehouse_master),
            "cost_config": str(init.input_paths.cost_config),
            "transfer_plan": str(init.input_paths.transfer_plan),
            "inventory_daily_state": str(init.input_paths.inventory_daily_state),
            "candidate_pool_base": str(init.input_paths.candidate_pool_base),
            "fdc_sku_daily_demand": str(init.input_paths.fdc_sku_daily_demand),
            "policy": init.config["policy"]["path"],
            "rules": init.config["rules"]["path"],
        },
        "version_lineage": {
            "experiment_id": context.experiment_id,
            "data_version": context.data_version,
            "assortment_version": context.assortment_version,
            "policy_version": context.policy_version,
            "simulation_rule_version": context.simulation_rule_version,
            "config_path": str(config_path),
            "assortment_source": str(init.input_paths.candidate_pool_base),
            "policy_path": init.config["policy"]["path"],
            "rules_path": init.config["rules"]["path"],
        },
        "initialization": {
            "initial_inventory_rows": init.initial_inventory_rows,
            "initial_pipeline_events": init.initial_pipeline_events,
            "initial_pipeline_qty": init.initial_pipeline_qty,
        },
        "row_counts": row_counts,
        "metrics_summary": metrics_summary,
        "outputs": outputs,
        "replay_command": f"PYTHONPATH=. python3 simulation/scripts/run_simulation.py --config {config_path}",
    }


def write_report(
    report_path: Path,
    manifest: dict[str, Any],
    metrics_summary: dict[str, Any],
    daily_logs: list[dict[str, Any]],
) -> None:
    first_days = daily_logs[:3]
    last_days = daily_logs[-3:] if len(daily_logs) > 3 else []
    lines = [
        f"# Simulation Report: {manifest['experiment_id']}",
        "",
        f"- data_version: {manifest['data_version']}",
        f"- assortment_version: {manifest['assortment_version']}",
        f"- policy_version: {manifest['policy_version']}",
        f"- simulation_rule_version: {manifest['simulation_rule_version']}",
        f"- date_range: {manifest['simulation_start_date']} to {manifest['simulation_end_date']}",
        "",
        "## Metrics Summary",
        "",
        "```json",
        json.dumps(metrics_summary, ensure_ascii=False, indent=2),
        "```",
        "",
        "## Output Row Counts",
        "",
        "```json",
        json.dumps(manifest["row_counts"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## Daily Log Sample",
        "",
        "```json",
        json.dumps({"first_days": first_days, "last_days": last_days}, ensure_ascii=False, indent=2),
        "```",
    ]
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
