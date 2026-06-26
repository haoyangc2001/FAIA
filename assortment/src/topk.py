"""Top-K baseline assortment method."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Any

from assortment.src.common import as_bool, as_date_str, as_float, as_int, write_csv


TOPK_RESULT_FIELDS = [
    "experiment_id",
    "data_version",
    "candidate_pool_version",
    "k_rule_version",
    "method_version",
    "assortment_version",
    "anchor_date",
    "effective_start_date",
    "effective_end_date",
    "fdc_id",
    "rdc_id",
    "sku_id",
    "selected_flag",
    "rank",
    "score",
    "topk_score",
    "structure_score",
    "ml_score",
    "source_tag",
    "selected_k",
    "candidate_sku_count",
    "cumulative_volume",
]


def _load_candidate_rows(path: Path) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if not as_bool(row["candidate_flag"]):
                continue
            grouped[row["fdc_id"]].append(row)
    return grouped


def _load_k_table(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return {row["fdc_id"]: row for row in csv.DictReader(f)}


def build_topk_result(config: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    topk_cfg = config["topk"]
    candidate_by_fdc = _load_candidate_rows(run_dir / "candidate_pool.csv")
    k_by_fdc = _load_k_table(run_dir / "k_table.csv")
    score_field = topk_cfg.get("score_field", "historical_order_count")

    output_rows: list[dict[str, Any]] = []
    selected_counts: dict[str, int] = {}
    anchor_date = as_date_str(config["anchor_date"])
    effective_start_date = as_date_str(config["effective_start_date"])
    effective_end_date = as_date_str(config["effective_end_date"])

    for fdc_id in sorted(candidate_by_fdc):
        candidates = candidate_by_fdc[fdc_id]
        k_row = k_by_fdc[fdc_id]
        selected_k = as_int(k_row["selected_k"])
        candidate_count = as_int(k_row["candidate_sku_count"])
        ranked = sorted(
            candidates,
            key=lambda row: (
                -as_float(row.get(score_field, "0")),
                -as_float(row["future_promo_score"]),
                -as_float(row["static_priority_score"]),
                row["sku_id"],
            ),
        )

        cumulative_volume = 0.0
        for rank, row in enumerate(ranked[:selected_k], start=1):
            score = as_float(row.get(score_field, "0"))
            cumulative_volume += as_float(row["volume"])
            output_rows.append(
                {
                    "experiment_id": config["experiment_id"],
                    "data_version": config["data_version"],
                    "candidate_pool_version": config["candidate_pool_version"],
                    "k_rule_version": config["k_rule_version"],
                    "method_version": config["method_version"],
                    "assortment_version": config["assortment_version"],
                    "anchor_date": anchor_date,
                    "effective_start_date": effective_start_date,
                    "effective_end_date": effective_end_date,
                    "fdc_id": fdc_id,
                    "rdc_id": row["rdc_id"],
                    "sku_id": row["sku_id"],
                    "selected_flag": "true",
                    "rank": rank,
                    "score": round(score, 6),
                    "topk_score": round(score, 6),
                    "structure_score": "",
                    "ml_score": "",
                    "source_tag": "topk",
                    "selected_k": selected_k,
                    "candidate_sku_count": candidate_count,
                    "cumulative_volume": round(cumulative_volume, 6),
                }
            )
        selected_counts[fdc_id] = min(selected_k, len(ranked))

    row_count = write_csv(run_dir / "topk_result.csv", TOPK_RESULT_FIELDS, output_rows)
    return {
        "row_count": row_count,
        "fdc_count": len(selected_counts),
        "min_selected_rows": min(selected_counts.values()) if selected_counts else 0,
        "max_selected_rows": max(selected_counts.values()) if selected_counts else 0,
        "total_selected_rows": sum(selected_counts.values()),
    }
