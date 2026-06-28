"""Build decision-date inventory state for allocation policies."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from inventory.src.common import (
    bool_text,
    input_path,
    int_value,
    iter_csv_rows,
    parse_date,
    read_bool,
    write_csv,
)


INVENTORY_STATE_FIELDS = [
    "experiment_id",
    "data_version",
    "assortment_version",
    "inventory_version",
    "simulation_rule_version",
    "decision_date",
    "source_snapshot_date",
    "node_id",
    "node_type",
    "rdc_id",
    "fdc_id",
    "sku_id",
    "on_hand_qty",
    "reserved_qty",
    "available_qty",
    "in_transit_qty",
    "inventory_position_qty",
    "assortment_mask",
    "eligible_mask",
    "selected_rank",
    "lead_time_days",
    "fdc_capacity_units",
    "fdc_active_sku_count",
    "fdc_remaining_capacity_units",
    "rdc_reserved_qty",
    "rdc_allocatable_qty",
]


@dataclass(frozen=True)
class WarehouseContext:
    fdc_to_rdc: dict[str, str]
    fdc_capacity: dict[str, int]
    rdc_ids: set[str]


def load_warehouse_context(path: Path) -> WarehouseContext:
    fdc_to_rdc: dict[str, str] = {}
    fdc_capacity: dict[str, int] = {}
    rdc_ids: set[str] = set()
    for row in iter_csv_rows(path):
        node_id = row["node_id"]
        if row["node_type"] == "RDC":
            rdc_ids.add(node_id)
        elif row["node_type"] == "FDC":
            fdc_to_rdc[node_id] = row["rdc_id"]
            fdc_capacity[node_id] = int_value(row["capacity_units"])
    if not fdc_to_rdc:
        raise ValueError("warehouse_master contains no FDC rows")
    return WarehouseContext(fdc_to_rdc=fdc_to_rdc, fdc_capacity=fdc_capacity, rdc_ids=rdc_ids)


def load_assortment_pairs(path: Path, assortment_version: str, decision_date: str) -> dict[tuple[str, str], dict[str, str]]:
    pairs: dict[tuple[str, str], dict[str, str]] = {}
    for row in iter_csv_rows(path):
        if row.get("assortment_version") != assortment_version:
            continue
        if not read_bool(row.get("selected_flag", "false")):
            continue
        anchor_date = row.get("anchor_date", decision_date)
        if anchor_date != decision_date:
            continue
        pairs[(row["fdc_id"], row["sku_id"])] = row
    if not pairs:
        raise ValueError(
            f"assortment_result contains no selected pairs for assortment_version={assortment_version} "
            f"and decision_date={decision_date}"
        )
    return pairs


def load_eligible_pairs(path: Path) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for row in iter_csv_rows(path):
        if read_bool(row.get("eligible_flag", "false")):
            pairs.add((row["fdc_id"], row["sku_id"]))
    if not pairs:
        raise ValueError("sku_fdc_eligibility contains no eligible FDC-SKU pairs")
    return pairs


def load_inventory_snapshot(path: Path, snapshot_date: str) -> dict[tuple[str, str], dict[str, int | str]]:
    rows: dict[tuple[str, str], dict[str, int | str]] = {}
    for row in iter_csv_rows(path):
        if row["date"] != snapshot_date:
            continue
        node_id = row["node_id"]
        sku_id = row["sku_id"]
        on_hand = int_value(row["on_hand_qty"])
        reserved = int_value(row["reserved_qty"])
        available = int_value(row.get("available_qty", max(0, on_hand - reserved)))
        in_transit = int_value(row.get("in_transit_qty", 0))
        rows[(node_id, sku_id)] = {
            "node_type": row["node_type"],
            "on_hand_qty": on_hand,
            "reserved_qty": reserved,
            "available_qty": available,
            "in_transit_qty": in_transit,
            "inventory_position_qty": int_value(row.get("inventory_position_qty", available + in_transit)),
        }
    if not rows:
        raise ValueError(f"inventory_daily_state contains no rows for source_snapshot_date={snapshot_date}")
    return rows


def load_open_pipeline(path: Path, decision_date: str) -> dict[tuple[str, str], int]:
    decision_dt = parse_date(decision_date)
    pipeline: dict[tuple[str, str], int] = defaultdict(int)
    for row in iter_csv_rows(path):
        ship_dt = parse_date(row["ship_date"])
        arrival_dt = parse_date(row["arrival_date"])
        if ship_dt <= decision_dt < arrival_dt:
            pipeline[(row["fdc_id"], row["sku_id"])] += int_value(row["transfer_qty"])
    return dict(pipeline)


def active_sku_counts(
    inventory_rows: dict[tuple[str, str], dict[str, int | str]],
    pipeline_qty: dict[tuple[str, str], int],
) -> dict[str, int]:
    active: dict[str, set[str]] = defaultdict(set)
    for (node_id, sku_id), row in inventory_rows.items():
        if row["node_type"] != "FDC":
            continue
        position = int(row["available_qty"]) + int(row["in_transit_qty"]) + pipeline_qty.get((node_id, sku_id), 0)
        if position > 0:
            active[node_id].add(sku_id)
    for (fdc_id, sku_id), qty in pipeline_qty.items():
        if qty > 0:
            active[fdc_id].add(sku_id)
    return {fdc_id: len(sku_ids) for fdc_id, sku_ids in active.items()}


def build_inventory_state_rows(config: dict[str, Any]) -> list[dict[str, Any]]:
    decision_date = str(config["decision_date"])
    source_snapshot_date = str(config.get("state", {}).get("source_snapshot_date", config["initial_inventory_date"]))
    default_lead_time = int(config.get("state", {}).get("default_lead_time_days", 2))
    business_reserve = int(config.get("allocation", {}).get("rdc_business_reserve_qty_per_sku", 0))

    warehouse = load_warehouse_context(input_path(config, "warehouse_master"))
    selected_pairs = load_assortment_pairs(
        input_path(config, "assortment_result"),
        str(config["assortment_version"]),
        decision_date,
    )
    eligible_pairs = load_eligible_pairs(input_path(config, "sku_fdc_eligibility"))
    inventory_rows = load_inventory_snapshot(input_path(config, "inventory_daily_state"), source_snapshot_date)
    pipeline_qty = load_open_pipeline(input_path(config, "transfer_plan"), decision_date)
    active_counts = active_sku_counts(inventory_rows, pipeline_qty)

    selected_by_rdc_sku: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
    for (fdc_id, sku_id), row in selected_pairs.items():
        rdc_id = row.get("rdc_id") or warehouse.fdc_to_rdc[fdc_id]
        selected_by_rdc_sku[(rdc_id, sku_id)].append((fdc_id, sku_id))

    rdc_allocatable: dict[tuple[str, str], tuple[int, int, int]] = {}
    for rdc_sku in selected_by_rdc_sku:
        rdc_id, sku_id = rdc_sku
        snapshot = inventory_rows.get((rdc_id, sku_id), {})
        on_hand = int(snapshot.get("on_hand_qty", 0))
        reserved = max(business_reserve, int(snapshot.get("reserved_qty", 0)))
        allocatable = max(0, on_hand - reserved)
        rdc_allocatable[rdc_sku] = (on_hand, reserved, allocatable)

    rows: list[dict[str, Any]] = []
    if config.get("state", {}).get("include_rdc_nodes", True):
        for (rdc_id, sku_id), (on_hand, reserved, allocatable) in sorted(rdc_allocatable.items()):
            available = max(0, on_hand - reserved)
            rows.append(
                base_state_row(
                    config=config,
                    decision_date=decision_date,
                    source_snapshot_date=source_snapshot_date,
                    node_id=rdc_id,
                    node_type="RDC",
                    rdc_id=rdc_id,
                    fdc_id="",
                    sku_id=sku_id,
                    on_hand_qty=on_hand,
                    reserved_qty=reserved,
                    available_qty=available,
                    in_transit_qty=0,
                    assortment_mask=True,
                    eligible_mask=True,
                    selected_rank="",
                    lead_time_days=default_lead_time,
                    fdc_capacity_units="",
                    fdc_active_sku_count="",
                    fdc_remaining_capacity_units="",
                    rdc_reserved_qty=reserved,
                    rdc_allocatable_qty=allocatable,
                )
            )

    if config.get("state", {}).get("include_fdc_nodes", True):
        for (fdc_id, sku_id), assortment_row in sorted(selected_pairs.items()):
            rdc_id = assortment_row.get("rdc_id") or warehouse.fdc_to_rdc[fdc_id]
            snapshot = inventory_rows.get((fdc_id, sku_id), {})
            on_hand = int(snapshot.get("on_hand_qty", 0))
            reserved = int(snapshot.get("reserved_qty", 0))
            available = int(snapshot.get("available_qty", max(0, on_hand - reserved)))
            transfer_in_transit = pipeline_qty.get((fdc_id, sku_id))
            in_transit = transfer_in_transit if transfer_in_transit is not None else int(snapshot.get("in_transit_qty", 0))
            capacity = warehouse.fdc_capacity.get(fdc_id, 0)
            active_count = active_counts.get(fdc_id, 0)
            remaining_capacity = max(0, capacity - active_count)
            _rdc_on_hand, rdc_reserved, rdc_alloc = rdc_allocatable.get((rdc_id, sku_id), (0, business_reserve, 0))
            rows.append(
                base_state_row(
                    config=config,
                    decision_date=decision_date,
                    source_snapshot_date=source_snapshot_date,
                    node_id=fdc_id,
                    node_type="FDC",
                    rdc_id=rdc_id,
                    fdc_id=fdc_id,
                    sku_id=sku_id,
                    on_hand_qty=on_hand,
                    reserved_qty=reserved,
                    available_qty=available,
                    in_transit_qty=in_transit,
                    assortment_mask=True,
                    eligible_mask=(fdc_id, sku_id) in eligible_pairs,
                    selected_rank=assortment_row.get("rank", ""),
                    lead_time_days=default_lead_time,
                    fdc_capacity_units=capacity,
                    fdc_active_sku_count=active_count,
                    fdc_remaining_capacity_units=remaining_capacity,
                    rdc_reserved_qty=rdc_reserved,
                    rdc_allocatable_qty=rdc_alloc,
                )
            )

    return rows


def base_state_row(
    config: dict[str, Any],
    decision_date: str,
    source_snapshot_date: str,
    node_id: str,
    node_type: str,
    rdc_id: str,
    fdc_id: str,
    sku_id: str,
    on_hand_qty: int,
    reserved_qty: int,
    available_qty: int,
    in_transit_qty: int,
    assortment_mask: bool,
    eligible_mask: bool,
    selected_rank: object,
    lead_time_days: int,
    fdc_capacity_units: object,
    fdc_active_sku_count: object,
    fdc_remaining_capacity_units: object,
    rdc_reserved_qty: int,
    rdc_allocatable_qty: int,
) -> dict[str, Any]:
    return {
        "experiment_id": config["experiment_id"],
        "data_version": config["data_version"],
        "assortment_version": config["assortment_version"],
        "inventory_version": config["inventory_version"],
        "simulation_rule_version": config["simulation_rule_version"],
        "decision_date": decision_date,
        "source_snapshot_date": source_snapshot_date,
        "node_id": node_id,
        "node_type": node_type,
        "rdc_id": rdc_id,
        "fdc_id": fdc_id,
        "sku_id": sku_id,
        "on_hand_qty": on_hand_qty,
        "reserved_qty": reserved_qty,
        "available_qty": available_qty,
        "in_transit_qty": in_transit_qty,
        "inventory_position_qty": available_qty + in_transit_qty,
        "assortment_mask": bool_text(assortment_mask),
        "eligible_mask": bool_text(eligible_mask),
        "selected_rank": selected_rank,
        "lead_time_days": lead_time_days,
        "fdc_capacity_units": fdc_capacity_units,
        "fdc_active_sku_count": fdc_active_sku_count,
        "fdc_remaining_capacity_units": fdc_remaining_capacity_units,
        "rdc_reserved_qty": rdc_reserved_qty,
        "rdc_allocatable_qty": rdc_allocatable_qty,
    }


def write_inventory_state(config: dict[str, Any], rows: list[dict[str, Any]] | None = None) -> tuple[Path, int]:
    run_dir = Path(str(config["output"]["run_dir"]))
    output_path = run_dir / "inventory_state.csv"
    state_rows = rows if rows is not None else build_inventory_state_rows(config)
    count = write_csv(output_path, INVENTORY_STATE_FIELDS, state_rows)
    return output_path, count
