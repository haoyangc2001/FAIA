"""Lightweight ML-Top-K baseline for assortment selection.

The first implementation intentionally avoids external ML dependencies. It
fixes the ML-Top-K input/output contract and uses a deterministic linear score
over the stage-1 feature fields. Later model versions can replace the scoring
function while keeping ``ml_topk_result.csv`` stable.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Any

from assortment.src.common import as_bool, as_date_str, as_float, as_int, write_csv, write_yaml
from assortment.src.topk import TOPK_RESULT_FIELDS


ML_TOPK_RESULT_FIELDS = TOPK_RESULT_FIELDS


DEFAULT_ML_TOPK_CONFIG = {
    "method_version": "ml_topk_v001",
    "assortment_version": "assortment_ml_topk_v001",
    "model_version": "ml_topk_linear_v001",
    "history_7d_weight": 0.45,
    "history_14d_weight": 0.25,
    "history_30d_weight": 0.20,
    "history_60d_weight": 0.10,
    "future_promo_day_weight": 4.0,
    "future_campaign_day_weight": 0.25,
    "static_priority_weight": 10.0,
    "score_precision": 8,
}


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


def _load_anchor_features(path: Path | None, anchor_date: str) -> dict[tuple[str, str], dict[str, str]]:
    if path is None or not path.exists():
        return {}
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = set(reader.fieldnames or [])
        required = {"anchor_date", "fdc_id", "sku_id"}
        if not required.issubset(fieldnames):
            return {}
        features: dict[tuple[str, str], dict[str, str]] = {}
        for row in reader:
            if row["anchor_date"] == anchor_date:
                features[(row["fdc_id"], row["sku_id"])] = row
        return features


def _score_from_features(feature: dict[str, str], candidate: dict[str, str], cfg: dict[str, Any]) -> float:
    if feature:
        hist_7 = as_float(feature.get("hist_7d_orders"))
        hist_14_daily = as_float(feature.get("hist_14d_orders")) / 2.0
        hist_30_daily = as_float(feature.get("hist_30d_orders")) / (30.0 / 7.0)
        hist_60_daily = as_float(feature.get("hist_60d_orders")) / (60.0 / 7.0)
        history_score = (
            hist_7 * as_float(cfg["history_7d_weight"])
            + hist_14_daily * as_float(cfg["history_14d_weight"])
            + hist_30_daily * as_float(cfg["history_30d_weight"])
            + hist_60_daily * as_float(cfg["history_60d_weight"])
        )
        future_promo_score = (
            as_float(feature.get("future_promo_days_14d")) * as_float(cfg["future_promo_day_weight"])
            + as_float(feature.get("future_campaign_days_14d")) * as_float(cfg["future_campaign_day_weight"])
        )
        static_score = as_float(feature.get("base_popularity")) * as_float(cfg["static_priority_weight"])
        return max(0.0, history_score + future_promo_score + static_score)

    return max(
        0.0,
        as_float(candidate["historical_order_count"])
        + as_float(candidate["future_promo_score"]) * as_float(cfg["future_promo_day_weight"])
        + as_float(candidate["static_priority_score"]) * as_float(cfg["static_priority_weight"]),
    )


def build_ml_topk_result(config: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    """Build ``ml_topk_result.csv`` with a stable ML-Top-K result schema."""

    ml_cfg = {**DEFAULT_ML_TOPK_CONFIG, **(config.get("ml_topk", {}) or {})}
    anchor_date = as_date_str(config["anchor_date"])
    effective_start_date = as_date_str(config["effective_start_date"])
    effective_end_date = as_date_str(config["effective_end_date"])
    feature_path = config.get("inputs", {}).get("ml_topk_features")
    features = _load_anchor_features(Path(feature_path) if feature_path else None, anchor_date)
    candidate_by_fdc = _load_candidate_rows(run_dir / "candidate_pool.csv")
    k_by_fdc = _load_k_table(run_dir / "k_table.csv")

    output_rows: list[dict[str, Any]] = []
    selected_counts: dict[str, int] = {}
    feature_hit_count = 0
    scored_count = 0
    score_precision = as_int(ml_cfg.get("score_precision", 8), 8)

    for fdc_id in sorted(candidate_by_fdc):
        candidates = candidate_by_fdc[fdc_id]
        k_row = k_by_fdc[fdc_id]
        selected_k = as_int(k_row["selected_k"])
        candidate_count = as_int(k_row["candidate_sku_count"])
        scored_rows: list[tuple[float, dict[str, str]]] = []
        for row in candidates:
            feature = features.get((fdc_id, row["sku_id"]), {})
            if feature:
                feature_hit_count += 1
            score = _score_from_features(feature, row, ml_cfg)
            scored_count += 1
            scored_rows.append((score, row))

        ranked = sorted(
            scored_rows,
            key=lambda item: (
                -item[0],
                -as_float(item[1]["historical_order_count"]),
                -as_float(item[1]["future_promo_score"]),
                -as_float(item[1]["static_priority_score"]),
                item[1]["sku_id"],
            ),
        )

        cumulative_volume = 0.0
        for rank, (score, row) in enumerate(ranked[:selected_k], start=1):
            cumulative_volume += as_float(row["volume"])
            rounded_score = round(score, score_precision)
            output_rows.append(
                {
                    "experiment_id": config["experiment_id"],
                    "data_version": config["data_version"],
                    "candidate_pool_version": config["candidate_pool_version"],
                    "k_rule_version": config["k_rule_version"],
                    "method_version": ml_cfg["method_version"],
                    "assortment_version": ml_cfg["assortment_version"],
                    "anchor_date": anchor_date,
                    "effective_start_date": effective_start_date,
                    "effective_end_date": effective_end_date,
                    "fdc_id": fdc_id,
                    "rdc_id": row["rdc_id"],
                    "sku_id": row["sku_id"],
                    "selected_flag": "true",
                    "rank": rank,
                    "score": rounded_score,
                    "topk_score": row["historical_order_count"],
                    "structure_score": "",
                    "ml_score": rounded_score,
                    "source_tag": "ml_topk",
                    "selected_k": selected_k,
                    "candidate_sku_count": candidate_count,
                    "cumulative_volume": round(cumulative_volume, 6),
                }
            )
        selected_counts[fdc_id] = min(selected_k, len(ranked))

    row_count = write_csv(run_dir / "ml_topk_result.csv", ML_TOPK_RESULT_FIELDS, output_rows)
    model_manifest = {
        "model_version": ml_cfg["model_version"],
        "method_version": ml_cfg["method_version"],
        "assortment_version": ml_cfg["assortment_version"],
        "model_type": "deterministic_linear_baseline",
        "feature_path": str(feature_path or ""),
        "feature_rows_matched": feature_hit_count,
        "scored_candidate_rows": scored_count,
        "output": str(run_dir / "ml_topk_result.csv"),
        "score_formula": {
            "history_7d_weight": ml_cfg["history_7d_weight"],
            "history_14d_weight": ml_cfg["history_14d_weight"],
            "history_30d_weight": ml_cfg["history_30d_weight"],
            "history_60d_weight": ml_cfg["history_60d_weight"],
            "future_promo_day_weight": ml_cfg["future_promo_day_weight"],
            "future_campaign_day_weight": ml_cfg["future_campaign_day_weight"],
            "static_priority_weight": ml_cfg["static_priority_weight"],
        },
    }
    write_yaml(run_dir / "ml_topk_model_manifest.yaml", model_manifest)
    return {
        "row_count": row_count,
        "fdc_count": len(selected_counts),
        "min_selected_rows": min(selected_counts.values()) if selected_counts else 0,
        "max_selected_rows": max(selected_counts.values()) if selected_counts else 0,
        "total_selected_rows": sum(selected_counts.values()),
        "model_version": ml_cfg["model_version"],
        "feature_rows_matched": feature_hit_count,
        "scored_candidate_rows": scored_count,
        "model_manifest": str(run_dir / "ml_topk_model_manifest.yaml"),
    }
