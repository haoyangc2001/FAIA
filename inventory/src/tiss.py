"""Safety stock and target inventory generation."""

from __future__ import annotations

import math
from collections import defaultdict
from pathlib import Path
from typing import Any

from inventory.src.common import bool_text, float_value, int_value, read_bool, write_csv


TISS_RESULT_FIELDS = [
    "experiment_id",
    "data_version",
    "assortment_version",
    "inventory_version",
    "simulation_rule_version",
    "tiss_version",
    "model_version",
    "decision_date",
    "node_id",
    "node_type",
    "rdc_id",
    "fdc_id",
    "sku_id",
    "demand_forecast_qty",
    "forecast_daily_mean_qty",
    "historical_demand_std_qty",
    "lead_time_days",
    "replenishment_window_days",
    "service_factor",
    "demand_during_lead_time_qty",
    "uncertainty_buffer_qty",
    "safety_stock_qty",
    "target_inventory_qty",
    "current_inventory_position_qty",
    "assortment_mask",
    "eligible_mask",
    "constraint_projection_flag",
]


def build_tiss_rows(
    config: dict[str, Any],
    inventory_state_rows: list[dict[str, Any]],
    demand_forecast_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    tiss_cfg = config["tiss"]
    service_factor = float(tiss_cfg.get("service_factor", 1.28))
    replenishment_window_days = int(tiss_cfg.get("replenishment_window_days", 3))
    min_safety_stock = int(tiss_cfg.get("min_safety_stock_qty", 0))

    forecasts: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in demand_forecast_rows:
        forecasts[(str(row["node_id"]), str(row["sku_id"]))].append(row)

    rows: list[dict[str, Any]] = []
    for state in sorted(inventory_state_rows, key=lambda row: (row["node_type"], row["node_id"], row["sku_id"])):
        key = (str(state["node_id"]), str(state["sku_id"]))
        group = forecasts.get(key, [])
        demand_forecast_qty = sum(float_value(row["forecast_qty"]) for row in group[:replenishment_window_days])
        horizon = max(1, len(group))
        daily_mean = sum(float_value(row["forecast_qty"]) for row in group) / horizon if group else 0.0
        historical_std = max([float_value(row["historical_std_qty"]) for row in group], default=0.0)
        lead_time = int_value(state["lead_time_days"])
        demand_during_lead_time = daily_mean * lead_time
        uncertainty_buffer = service_factor * historical_std * math.sqrt(max(lead_time, 0))

        safety_stock = max(min_safety_stock, math.ceil(demand_during_lead_time + uncertainty_buffer))
        target_inventory = max(safety_stock, safety_stock + math.ceil(daily_mean * replenishment_window_days))

        assortment_mask = read_bool(state["assortment_mask"])
        eligible_mask = read_bool(state["eligible_mask"])
        projected = False
        if state["node_type"] == "FDC" and (not assortment_mask or not eligible_mask):
            projected = safety_stock != 0 or target_inventory != 0
            safety_stock = 0
            target_inventory = 0

        rows.append(
            {
                "experiment_id": config["experiment_id"],
                "data_version": config["data_version"],
                "assortment_version": config["assortment_version"],
                "inventory_version": config["inventory_version"],
                "simulation_rule_version": config["simulation_rule_version"],
                "tiss_version": tiss_cfg.get("tiss_version", "rule_tiss_v001"),
                "model_version": tiss_cfg.get("model_version", "none"),
                "decision_date": config["decision_date"],
                "node_id": state["node_id"],
                "node_type": state["node_type"],
                "rdc_id": state["rdc_id"],
                "fdc_id": state["fdc_id"],
                "sku_id": state["sku_id"],
                "demand_forecast_qty": round(demand_forecast_qty, 6),
                "forecast_daily_mean_qty": round(daily_mean, 6),
                "historical_demand_std_qty": round(historical_std, 6),
                "lead_time_days": lead_time,
                "replenishment_window_days": replenishment_window_days,
                "service_factor": service_factor,
                "demand_during_lead_time_qty": round(demand_during_lead_time, 6),
                "uncertainty_buffer_qty": round(uncertainty_buffer, 6),
                "safety_stock_qty": safety_stock,
                "target_inventory_qty": target_inventory,
                "current_inventory_position_qty": state["inventory_position_qty"],
                "assortment_mask": bool_text(assortment_mask),
                "eligible_mask": bool_text(eligible_mask),
                "constraint_projection_flag": bool_text(projected),
            }
        )
    return rows


def write_tiss_result(config: dict[str, Any], rows: list[dict[str, Any]]) -> tuple[Path, int]:
    run_dir = Path(str(config["output"]["run_dir"]))
    output_path = run_dir / "tiss_result.csv"
    count = write_csv(output_path, TISS_RESULT_FIELDS, rows)
    return output_path, count
