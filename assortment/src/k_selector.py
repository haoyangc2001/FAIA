"""Compute FDC-level K values for assortment selection."""

from __future__ import annotations

import csv
import math
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from assortment.src.common import as_bool, as_date_str, as_float, as_int, write_csv


K_TABLE_FIELDS = [
    "experiment_id",
    "data_version",
    "candidate_pool_version",
    "k_rule_version",
    "anchor_date",
    "effective_start_date",
    "effective_end_date",
    "fdc_id",
    "rdc_id",
    "candidate_sku_count",
    "target_order_coverage",
    "capacity_volume_limit",
    "avg_selected_sku_volume",
    "physical_capacity_k",
    "coverage_target_k",
    "min_k",
    "max_k",
    "selected_k",
    "k_source",
    "historical_window_start",
    "historical_window_end",
]


def _load_fdc_capacity(path: Path) -> dict[str, float]:
    capacity: dict[str, float] = {}
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row["node_type"] != "FDC":
                continue
            capacity[row["node_id"]] = as_float(row["capacity_units"])
    return capacity


def _load_candidate_rows(path: Path) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if not as_bool(row["candidate_flag"]):
                continue
            grouped[row["fdc_id"]].append(row)
    return grouped


def _coverage_target_k(rows: list[dict[str, str]], target_coverage: float, default_k: int) -> int:
    if not rows:
        return 0
    sorted_rows = sorted(
        rows,
        key=lambda row: (-as_int(row["historical_order_count"]), row["sku_id"]),
    )
    total_orders = sum(as_int(row["historical_order_count"]) for row in sorted_rows)
    if total_orders <= 0:
        return min(default_k, len(sorted_rows))
    running = 0
    for index, row in enumerate(sorted_rows, start=1):
        running += as_int(row["historical_order_count"])
        if running / total_orders >= target_coverage:
            return index
    return len(sorted_rows)


def _average_top_volume(rows: list[dict[str, str]], top_n: int) -> float:
    sorted_rows = sorted(
        rows,
        key=lambda row: (-as_int(row["historical_order_count"]), row["sku_id"]),
    )
    selected = sorted_rows[: max(1, min(top_n, len(sorted_rows)))]
    if not selected:
        return 1.0
    return sum(as_float(row["volume"], 1.0) for row in selected) / len(selected)


def build_k_table(config: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    k_cfg = config["k_rule"]
    candidate_by_fdc = _load_candidate_rows(run_dir / "candidate_pool.csv")
    fdc_capacity = _load_fdc_capacity(Path(config["inputs"]["warehouse_master"]))

    target_coverage = as_float(k_cfg["target_order_coverage"])
    configured_min_k = as_int(k_cfg["min_k"])
    configured_max_k = as_int(k_cfg["max_k"])
    default_k = as_int(k_cfg["default_k"])
    capacity_ratio = as_float(k_cfg["capacity_utilization_ratio"])
    avg_volume_top_n = as_int(k_cfg["avg_volume_top_n"])
    history_days = 60
    if str(config["candidate_pool"]["history_order_field"]).startswith("hist_"):
        history_days = as_int(str(config["candidate_pool"]["history_order_field"]).split("_")[1].replace("d", ""), 60)
    anchor_date = as_date_str(config["anchor_date"])
    effective_start_date = as_date_str(config["effective_start_date"])
    effective_end_date = as_date_str(config["effective_end_date"])
    anchor_dt = datetime.strptime(anchor_date, "%Y-%m-%d")
    historical_window_start = (anchor_dt - timedelta(days=history_days - 1)).strftime("%Y-%m-%d")

    rows: list[dict[str, Any]] = []
    selected_values: list[int] = []

    for fdc_id in sorted(candidate_by_fdc):
        candidates = candidate_by_fdc[fdc_id]
        candidate_count = len(candidates)
        rdc_id = candidates[0]["rdc_id"]
        capacity_volume_limit = fdc_capacity.get(fdc_id, 0.0) * capacity_ratio
        avg_volume = _average_top_volume(candidates, avg_volume_top_n)
        physical_capacity_k = min(candidate_count, max(0, math.floor(capacity_volume_limit / avg_volume)))
        coverage_k = _coverage_target_k(candidates, target_coverage, default_k)
        max_k = min(configured_max_k, candidate_count)
        min_k = min(configured_min_k, max_k, physical_capacity_k)
        desired_k = max(min_k, coverage_k)
        selected_k = min(candidate_count, max_k, physical_capacity_k, desired_k)

        if selected_k == physical_capacity_k and physical_capacity_k < coverage_k:
            k_source = "capacity"
        elif selected_k == max_k and coverage_k > max_k:
            k_source = "clipped"
        elif coverage_k <= 0:
            k_source = "default"
        else:
            k_source = "coverage"

        selected_values.append(selected_k)
        rows.append(
            {
                "experiment_id": config["experiment_id"],
                "data_version": config["data_version"],
                "candidate_pool_version": config["candidate_pool_version"],
                "k_rule_version": config["k_rule_version"],
                "anchor_date": anchor_date,
                "effective_start_date": effective_start_date,
                "effective_end_date": effective_end_date,
                "fdc_id": fdc_id,
                "rdc_id": rdc_id,
                "candidate_sku_count": candidate_count,
                "target_order_coverage": target_coverage,
                "capacity_volume_limit": round(capacity_volume_limit, 6),
                "avg_selected_sku_volume": round(avg_volume, 6),
                "physical_capacity_k": physical_capacity_k,
                "coverage_target_k": coverage_k,
                "min_k": min_k,
                "max_k": max_k,
                "selected_k": selected_k,
                "k_source": k_source,
                "historical_window_start": historical_window_start,
                "historical_window_end": anchor_date,
            }
        )

    row_count = write_csv(run_dir / "k_table.csv", K_TABLE_FIELDS, rows)
    return {
        "row_count": row_count,
        "fdc_count": row_count,
        "total_selected_k": sum(selected_values),
        "min_selected_k": min(selected_values) if selected_values else 0,
        "max_selected_k": max(selected_values) if selected_values else 0,
        "avg_selected_k": round(sum(selected_values) / len(selected_values), 4) if selected_values else 0,
    }
