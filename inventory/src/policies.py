"""Inventory allocation baseline policies."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from inventory.src.allocator import apply_rdc_reserve_and_greedy_allocation
from inventory.src.common import add_days, bool_text, float_value, int_value, read_bool, write_csv


TRANSFER_RECOMMENDATION_FIELDS = [
    "experiment_id",
    "data_version",
    "assortment_version",
    "inventory_version",
    "simulation_rule_version",
    "policy_name",
    "policy_version",
    "model_version",
    "run_date",
    "decision_date",
    "effective_date",
    "transfer_id",
    "rdc_id",
    "fdc_id",
    "sku_id",
    "demand_forecast_qty",
    "safety_stock_qty",
    "target_inventory_qty",
    "current_inventory_qty",
    "pipeline_inventory_qty",
    "inventory_position_qty",
    "rdc_on_hand_qty",
    "rdc_reserved_qty",
    "rdc_allocatable_qty",
    "priority_score",
    "recommended_transfer_qty",
    "actual_transfer_qty",
    "clipped_qty",
    "clip_reason",
    "ship_date",
    "arrival_date",
    "lead_time_days",
    "status",
    "reason",
    "assortment_mask",
    "eligible_mask",
]


def generate_transfer_recommendation_rows(
    config: dict[str, Any],
    inventory_state_rows: list[dict[str, Any]],
    tiss_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    policy_name = str(config["policy"].get("policy_name", "base_stock"))
    if policy_name == "no_transfer":
        return []
    if policy_name not in {"historical_mean", "base_stock", "parameter_search", "greedy_allocation", "model"}:
        raise ValueError(f"unsupported inventory policy_name: {policy_name}")

    base_rows = build_base_stock_gaps(config, inventory_state_rows, tiss_rows, historical_only=policy_name == "historical_mean")
    if not config["policy"].get("use_greedy_allocation", True) and policy_name != "greedy_allocation":
        return mark_without_greedy(base_rows)
    return apply_rdc_reserve_and_greedy_allocation(config, base_rows, tiss_rows)


def build_base_stock_gaps(
    config: dict[str, Any],
    inventory_state_rows: list[dict[str, Any]],
    tiss_rows: list[dict[str, Any]],
    historical_only: bool = False,
) -> list[dict[str, Any]]:
    state_by_fdc_sku = {
        (str(row["fdc_id"]), str(row["sku_id"])): row
        for row in inventory_state_rows
        if row["node_type"] == "FDC"
    }
    rdc_state = {
        (str(row["rdc_id"]), str(row["sku_id"])): row
        for row in inventory_state_rows
        if row["node_type"] == "RDC"
    }
    fdc_tiss = [row for row in tiss_rows if row["node_type"] == "FDC"]

    rows: list[dict[str, Any]] = []
    min_transfer = int(config["policy"].get("min_transfer_qty", 1))
    max_transfer = int(config["policy"].get("max_transfer_qty_per_sku", 300))
    for index, tiss in enumerate(sorted(fdc_tiss, key=lambda row: (row["fdc_id"], row["sku_id"])), start=1):
        state = state_by_fdc_sku.get((str(tiss["fdc_id"]), str(tiss["sku_id"])))
        if not state:
            continue
        if not read_bool(tiss["assortment_mask"]) or not read_bool(tiss["eligible_mask"]):
            continue
        current_position = int_value(state["inventory_position_qty"])
        target_inventory = int_value(tiss["target_inventory_qty"])
        safety_stock = int_value(tiss["safety_stock_qty"])
        if historical_only:
            target_inventory = max(0, int(round(float_value(tiss["forecast_daily_mean_qty"]) * int(config["tiss"].get("replenishment_window_days", 3)))))
            safety_stock = 0
        recommended = max(0, target_inventory - current_position)
        recommended = min(recommended, max_transfer)
        if recommended < min_transfer:
            continue

        rdc_key = (str(tiss["rdc_id"]), str(tiss["sku_id"]))
        rdc = rdc_state.get(rdc_key, {})
        lead_time = int_value(tiss["lead_time_days"])
        rows.append(
            {
                "experiment_id": config["experiment_id"],
                "data_version": config["data_version"],
                "assortment_version": config["assortment_version"],
                "inventory_version": config["inventory_version"],
                "simulation_rule_version": config["simulation_rule_version"],
                "policy_name": config["policy"].get("policy_name", "base_stock"),
                "policy_version": config["policy"].get("policy_version", "inventory_base_stock_v001"),
                "model_version": config["policy"].get("model_version", "none"),
                "run_date": config["decision_date"],
                "decision_date": config["decision_date"],
                "effective_date": config["effective_start_date"],
                "transfer_id": f"INVT{str(config['decision_date']).replace('-', '')}{index:010d}",
                "rdc_id": tiss["rdc_id"],
                "fdc_id": tiss["fdc_id"],
                "sku_id": tiss["sku_id"],
                "demand_forecast_qty": tiss["demand_forecast_qty"],
                "safety_stock_qty": safety_stock,
                "target_inventory_qty": target_inventory,
                "current_inventory_qty": state["on_hand_qty"],
                "pipeline_inventory_qty": state["in_transit_qty"],
                "inventory_position_qty": current_position,
                "rdc_on_hand_qty": rdc.get("on_hand_qty", state.get("rdc_allocatable_qty", 0)),
                "rdc_reserved_qty": rdc.get("rdc_reserved_qty", state.get("rdc_reserved_qty", 0)),
                "rdc_allocatable_qty": rdc.get("rdc_allocatable_qty", state.get("rdc_allocatable_qty", 0)),
                "priority_score": 0.0,
                "recommended_transfer_qty": recommended,
                "actual_transfer_qty": "",
                "clipped_qty": "",
                "clip_reason": "",
                "ship_date": config["effective_start_date"],
                "arrival_date": add_days(str(config["effective_start_date"]), lead_time),
                "lead_time_days": lead_time,
                "status": "recommended",
                "reason": "below_safety_stock" if current_position < safety_stock else "target_inventory_gap",
                "assortment_mask": bool_text(read_bool(tiss["assortment_mask"])),
                "eligible_mask": bool_text(read_bool(tiss["eligible_mask"])),
            }
        )
    return rows


def mark_without_greedy(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        row = dict(row)
        row["actual_transfer_qty"] = row["recommended_transfer_qty"]
        row["clipped_qty"] = 0
        row["clip_reason"] = ""
        row["status"] = "planned"
        result.append(row)
    return result


def write_transfer_recommendation(config: dict[str, Any], rows: list[dict[str, Any]]) -> tuple[Path, int]:
    run_dir = Path(str(config["output"]["run_dir"]))
    output_path = run_dir / "transfer_recommendation.csv"
    count = write_csv(output_path, TRANSFER_RECOMMENDATION_FIELDS, rows)
    return output_path, count
