"""RDC reserve and greedy allocation utilities."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from inventory.src.common import float_value, input_path, int_value, iter_csv_rows


def load_cost_values(path: Path) -> dict[str, float]:
    values: dict[str, float] = {}
    for row in iter_csv_rows(path):
        values[row["cost_item"]] = float_value(row["value"])
    return values


def rdc_safety_stock_by_sku(tiss_rows: list[dict[str, Any]]) -> dict[tuple[str, str], int]:
    result: dict[tuple[str, str], int] = {}
    for row in tiss_rows:
        if row["node_type"] != "RDC":
            continue
        result[(str(row["rdc_id"]), str(row["sku_id"]))] = int_value(row["safety_stock_qty"])
    return result


def compute_priority_score(
    recommendation: dict[str, Any],
    config: dict[str, Any],
    cost_values: dict[str, float],
) -> float:
    weights = config.get("allocation", {}).get("priority_score", {})
    demand = float_value(recommendation["demand_forecast_qty"])
    lost_sales_cost = cost_values.get("lost_sales_cost", 1.0)
    numerator = (
        demand
        * float(weights.get("demand_weight", 1.0))
        * lost_sales_cost
        * float(weights.get("lost_sales_cost_weight", 1.0))
        * float(weights.get("promotion_weight", 1.0))
    )
    denominator = max(float_value(recommendation["inventory_position_qty"]) * float(weights.get("inventory_position_penalty", 1.0)), 1.0)
    return max(0.0, numerator / denominator)


def apply_rdc_reserve_and_greedy_allocation(
    config: dict[str, Any],
    recommendations: list[dict[str, Any]],
    tiss_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not recommendations:
        return []

    cost_values = load_cost_values(input_path(config, "cost_config"))
    rdc_ss = rdc_safety_stock_by_sku(tiss_rows)
    business_reserve = int(config.get("allocation", {}).get("rdc_business_reserve_qty_per_sku", 0))

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for rec in recommendations:
        key = (str(rec["rdc_id"]), str(rec["sku_id"]))
        rec = dict(rec)
        reserve = max(business_reserve, rdc_ss.get(key, int_value(rec["rdc_reserved_qty"])))
        allocatable = max(0, int_value(rec["rdc_on_hand_qty"]) - reserve)
        rec["rdc_reserved_qty"] = reserve
        rec["rdc_allocatable_qty"] = allocatable
        rec["priority_score"] = round(compute_priority_score(rec, config, cost_values), 8)
        grouped[key].append(rec)

    allocated: list[dict[str, Any]] = []
    for _key, recs in sorted(grouped.items()):
        available = max(int_value(recs[0]["rdc_allocatable_qty"]), 0)
        ordered = sorted(
            recs,
            key=lambda rec: (
                -float_value(rec["priority_score"]),
                str(rec["fdc_id"]),
                str(rec["sku_id"]),
            ),
        )
        for rec in ordered:
            requested = int_value(rec["recommended_transfer_qty"])
            actual = min(requested, available)
            available -= actual
            clipped = max(0, requested - actual)
            if actual == requested:
                status = "planned"
                reason = rec.get("reason", "")
                clip_reason = ""
            elif actual > 0:
                status = "clipped"
                reason = rec.get("reason", "")
                clip_reason = "rdc_reserve_or_greedy_limit"
            else:
                status = "cancelled"
                reason = rec.get("reason", "")
                clip_reason = "rdc_reserve_or_greedy_limit"
            rec["actual_transfer_qty"] = actual
            rec["clipped_qty"] = clipped
            rec["clip_reason"] = clip_reason
            rec["status"] = status
            rec["reason"] = reason
            allocated.append(rec)

    return sorted(allocated, key=lambda rec: str(rec["transfer_id"]))
