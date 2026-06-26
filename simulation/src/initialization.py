"""Initialization helpers for the FAIA simulator."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from simulation.src.allocation import parse_date, validate_transfer_event
from simulation.src.state import SimulationContext, SimulationState, TransferEvent


@dataclass(frozen=True)
class SimulationInputPaths:
    warehouse_master: Path
    cost_config: Path
    transfer_plan: Path
    inventory_daily_state: Path
    candidate_pool_base: Path
    fdc_sku_daily_demand: Path


@dataclass
class SimulationInitialization:
    context: SimulationContext
    state: SimulationState
    input_paths: SimulationInputPaths
    config: dict[str, Any]
    rules: dict[str, Any]
    initial_inventory_rows: int
    initial_pipeline_events: int
    initial_pipeline_qty: int


def read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_simulation_config(config_path: Path) -> dict[str, Any]:
    config = read_yaml(config_path)
    required = [
        "experiment_id",
        "data_version",
        "assortment_version",
        "policy_version",
        "simulation_rule_version",
        "simulation_start_date",
        "simulation_end_date",
        "initial_inventory_date",
        "inputs",
        "rules",
    ]
    missing = [name for name in required if name not in config]
    if missing:
        raise ValueError(f"simulation config missing required fields: {missing}")
    return config


def resolve_input_paths(config: dict[str, Any]) -> SimulationInputPaths:
    inputs = config["inputs"]
    return SimulationInputPaths(
        warehouse_master=Path(inputs["warehouse_master"]),
        cost_config=Path(inputs["cost_config"]),
        transfer_plan=Path(inputs["transfer_plan"]),
        inventory_daily_state=Path(inputs["inventory_daily_state"]),
        candidate_pool_base=Path(inputs["candidate_pool_base"]),
        fdc_sku_daily_demand=Path(inputs["fdc_sku_daily_demand"]),
    )


def load_warehouse_context(path: Path) -> tuple[dict[str, str], dict[str, int]]:
    fdc_to_rdc: dict[str, str] = {}
    fdc_capacity: dict[str, int] = {}
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row["node_type"] == "FDC":
                fdc_to_rdc[row["node_id"]] = row["rdc_id"]
                fdc_capacity[row["node_id"]] = int(row["capacity_units"])
    if not fdc_to_rdc:
        raise ValueError("warehouse_master contains no FDC rows")
    return fdc_to_rdc, fdc_capacity


def load_candidate_pairs(path: Path) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row.get("eligible_flag", "true") == "true":
                pairs.add((row["fdc_id"], row["sku_id"]))
    if not pairs:
        raise ValueError("candidate_pool_base contains no eligible FDC-SKU pairs")
    return pairs


def load_initial_inventory_rows(path: Path, initial_inventory_date: str) -> list[dict[str, str]]:
    rows = []
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row["date"] == initial_inventory_date:
                rows.append(row)
    if not rows:
        raise ValueError(f"no inventory rows found for initial_inventory_date={initial_inventory_date}")
    return rows


def load_open_pipeline_events(path: Path, initial_inventory_date: str) -> list[TransferEvent]:
    """Load transfers already shipped but not arrived by the initial inventory date.

    The v001 inventory snapshots are end-of-day states. Therefore transfers with
    arrival_date <= initial_inventory_date have already been reflected in
    on-hand inventory and should not be loaded into the opening pipeline.
    """

    initial_dt = parse_date(initial_inventory_date)
    events: list[TransferEvent] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            ship_dt = parse_date(row["ship_date"])
            arrival_dt = parse_date(row["arrival_date"])
            if ship_dt <= initial_dt < arrival_dt:
                event = TransferEvent(
                    ship_date=row["ship_date"],
                    arrival_date=row["arrival_date"],
                    rdc_id=row["rdc_id"],
                    fdc_id=row["fdc_id"],
                    sku_id=row["sku_id"],
                    qty=int(row["transfer_qty"]),
                    lead_time_days=int(row["lead_time_days"]),
                )
                validate_transfer_event(event)
                events.append(event)
    return events


def build_simulation_context(config: dict[str, Any], input_paths: SimulationInputPaths) -> SimulationContext:
    fdc_to_rdc, fdc_capacity = load_warehouse_context(input_paths.warehouse_master)
    eligible_pairs = load_candidate_pairs(input_paths.candidate_pool_base)
    return SimulationContext(
        experiment_id=config["experiment_id"],
        data_version=config["data_version"],
        assortment_version=config["assortment_version"],
        policy_version=config["policy_version"],
        simulation_rule_version=config["simulation_rule_version"],
        simulation_start_date=str(config["simulation_start_date"]),
        simulation_end_date=str(config["simulation_end_date"]),
        fdc_to_rdc=fdc_to_rdc,
        fdc_capacity=fdc_capacity,
        eligible_pairs=eligible_pairs,
    )


def initialize_simulation(config_path: Path) -> SimulationInitialization:
    config = load_simulation_config(config_path)
    rules = read_yaml(Path(config["rules"]["path"]))
    if rules["simulation_rule_version"] != config["simulation_rule_version"]:
        raise ValueError(
            "simulation_rule_version mismatch between config and rules: "
            f"{config['simulation_rule_version']} != {rules['simulation_rule_version']}"
        )

    input_paths = resolve_input_paths(config)
    context = build_simulation_context(config, input_paths)
    initial_inventory_date = str(config["initial_inventory_date"])
    inventory_rows = load_initial_inventory_rows(input_paths.inventory_daily_state, initial_inventory_date)
    state = SimulationState.from_inventory_rows(initial_inventory_date, inventory_rows)

    pipeline_events = load_open_pipeline_events(input_paths.transfer_plan, initial_inventory_date)
    for event in pipeline_events:
        state.add_pipeline_transfer(event)
    state.validate_non_negative()

    return SimulationInitialization(
        context=context,
        state=state,
        input_paths=input_paths,
        config=config,
        rules=rules,
        initial_inventory_rows=len(inventory_rows),
        initial_pipeline_events=len(pipeline_events),
        initial_pipeline_qty=sum(event.qty for event in pipeline_events),
    )


def initialization_summary(init: SimulationInitialization) -> dict[str, Any]:
    return {
        "experiment_id": init.context.experiment_id,
        "data_version": init.context.data_version,
        "assortment_version": init.context.assortment_version,
        "policy_version": init.context.policy_version,
        "simulation_rule_version": init.context.simulation_rule_version,
        "simulation_start_date": init.context.simulation_start_date,
        "simulation_end_date": init.context.simulation_end_date,
        "state_current_date": init.state.current_date,
        "fdc_count": len(init.context.fdc_to_rdc),
        "candidate_pair_count": len(init.context.eligible_pairs),
        "rdc_inventory_cells": len(init.state.rdc_on_hand_inventory),
        "fdc_inventory_cells": len(init.state.fdc_on_hand_inventory),
        "initial_inventory_rows": init.initial_inventory_rows,
        "initial_pipeline_events": init.initial_pipeline_events,
        "initial_pipeline_qty": init.initial_pipeline_qty,
        "pipeline_arrival_dates": sorted(init.state.pipeline_inventory),
    }
