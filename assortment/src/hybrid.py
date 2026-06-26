"""Hybrid assortment method combining Top-K and Reverse-Exclude signals."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Any

from assortment.src.common import as_bool, as_date_str, as_float, as_int, write_csv


HYBRID_RESULT_FIELDS = [
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


def _load_reverse_scores(path: Path) -> dict[tuple[str, str], float]:
    scores: dict[tuple[str, str], float] = {}
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            scores[(row["fdc_id"], row["sku_id"])] = as_float(row["structure_score"])
    return scores


def _load_method_rankings(path: Path) -> tuple[dict[str, list[str]], dict[tuple[str, str], int]]:
    rankings: dict[str, list[tuple[int, str]]] = defaultdict(list)
    ranks: dict[tuple[str, str], int] = {}
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            rank = as_int(row["rank"])
            rankings[row["fdc_id"]].append((rank, row["sku_id"]))
            ranks[(row["fdc_id"], row["sku_id"])] = rank
    return {
        fdc_id: [sku_id for _, sku_id in sorted(values)]
        for fdc_id, values in rankings.items()
    }, ranks


def _normalize(value: float, max_value: float) -> float:
    if max_value <= 0:
        return 0.0
    return value / max_value


def _select_alternating_union(
    selected_k: int,
    topk_ranked_skus: list[str],
    reverse_ranked_skus: list[str],
    fallback_ranked_skus: list[str],
) -> list[str]:
    selected: list[str] = []
    selected_set: set[str] = set()
    topk_index = 0
    reverse_index = 0

    def add_next(source: list[str], index: int) -> tuple[int, bool]:
        while index < len(source):
            sku_id = source[index]
            index += 1
            if sku_id in selected_set:
                continue
            selected.append(sku_id)
            selected_set.add(sku_id)
            return index, True
        return index, False

    while len(selected) < selected_k and (topk_index < len(topk_ranked_skus) or reverse_index < len(reverse_ranked_skus)):
        topk_index, topk_added = add_next(topk_ranked_skus, topk_index)
        if len(selected) >= selected_k:
            break
        reverse_index, reverse_added = add_next(reverse_ranked_skus, reverse_index)
        if not topk_added and not reverse_added:
            break

    if len(selected) < selected_k:
        for sku_id in fallback_ranked_skus:
            if sku_id in selected_set:
                continue
            selected.append(sku_id)
            selected_set.add(sku_id)
            if len(selected) >= selected_k:
                break
    return selected


def build_hybrid_result(config: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    hybrid_cfg = config["hybrid"]
    candidate_by_fdc = _load_candidate_rows(run_dir / "candidate_pool.csv")
    k_by_fdc = _load_k_table(run_dir / "k_table.csv")
    reverse_scores = _load_reverse_scores(run_dir / "reverse_exclude_result.csv")
    topk_rankings, topk_ranks = _load_method_rankings(run_dir / "topk_result.csv")
    reverse_rankings, reverse_ranks = _load_method_rankings(run_dir / "reverse_exclude_result.csv")

    topk_weight = as_float(hybrid_cfg["topk_weight"])
    reverse_weight = as_float(hybrid_cfg["reverse_weight"])
    score_precision = as_int(hybrid_cfg.get("score_precision", 8), 8)
    method_version = hybrid_cfg["method_version"]
    assortment_version = hybrid_cfg["assortment_version"]
    anchor_date = as_date_str(config["anchor_date"])
    effective_start_date = as_date_str(config["effective_start_date"])
    effective_end_date = as_date_str(config["effective_end_date"])

    output_rows: list[dict[str, Any]] = []
    selected_counts: dict[str, int] = {}
    topk_overlap_counts: dict[str, int] = {}
    reverse_overlap_counts: dict[str, int] = {}

    for fdc_id in sorted(candidate_by_fdc):
        candidates = candidate_by_fdc[fdc_id]
        k_row = k_by_fdc[fdc_id]
        selected_k = as_int(k_row["selected_k"])
        candidate_count = as_int(k_row["candidate_sku_count"])
        candidate_by_sku = {row["sku_id"]: row for row in candidates}

        max_topk_score = max((as_float(row["historical_order_count"]) for row in candidates), default=0.0)
        max_structure_score = max(
            (reverse_scores.get((fdc_id, row["sku_id"]), 0.0) for row in candidates),
            default=0.0,
        )

        scored_rows: list[tuple[float, float, float, dict[str, str]]] = []
        for row in candidates:
            topk_score = as_float(row["historical_order_count"])
            structure_score = reverse_scores.get((fdc_id, row["sku_id"]), 0.0)
            topk_norm = _normalize(topk_score, max_topk_score)
            structure_norm = _normalize(structure_score, max_structure_score)
            hybrid_score = topk_weight * topk_norm + reverse_weight * structure_norm
            scored_rows.append((hybrid_score, topk_score, structure_score, row))

        fallback_ranked_skus = [
            row["sku_id"]
            for _, _, _, row in sorted(
                scored_rows,
                key=lambda item: (
                    -item[0],
                    -item[1],
                    -item[2],
                    -as_float(item[3]["future_promo_score"]),
                    -as_float(item[3]["static_priority_score"]),
                    item[3]["sku_id"],
                ),
            )
        ]
        selected_skus = _select_alternating_union(
            selected_k,
            topk_rankings.get(fdc_id, []),
            reverse_rankings.get(fdc_id, []),
            fallback_ranked_skus,
        )
        selected_rows = []
        for sku_id in selected_skus:
            row = candidate_by_sku[sku_id]
            topk_score = as_float(row["historical_order_count"])
            structure_score = reverse_scores.get((fdc_id, sku_id), 0.0)
            topk_norm = _normalize(topk_score, max_topk_score)
            structure_norm = _normalize(structure_score, max_structure_score)
            hybrid_score = topk_weight * topk_norm + reverse_weight * structure_norm
            selected_rows.append((hybrid_score, topk_score, structure_score, row))

        selected_rows.sort(
            key=lambda item: (
                -item[0],
                -item[1],
                -item[2],
                -as_float(item[3]["future_promo_score"]),
                -as_float(item[3]["static_priority_score"]),
                item[3]["sku_id"],
            )
        )
        selected_counts[fdc_id] = len(selected_rows)
        topk_overlap_counts[fdc_id] = sum(1 for _, _, _, row in selected_rows if (fdc_id, row["sku_id"]) in topk_ranks)
        reverse_overlap_counts[fdc_id] = sum(1 for _, _, _, row in selected_rows if (fdc_id, row["sku_id"]) in reverse_ranks)

        cumulative_volume = 0.0
        for rank, (hybrid_score, topk_score, structure_score, row) in enumerate(selected_rows, start=1):
            cumulative_volume += as_float(row["volume"])
            output_rows.append(
                {
                    "experiment_id": config["experiment_id"],
                    "data_version": config["data_version"],
                    "candidate_pool_version": config["candidate_pool_version"],
                    "k_rule_version": config["k_rule_version"],
                    "method_version": method_version,
                    "assortment_version": assortment_version,
                    "anchor_date": anchor_date,
                    "effective_start_date": effective_start_date,
                    "effective_end_date": effective_end_date,
                    "fdc_id": fdc_id,
                    "rdc_id": row["rdc_id"],
                    "sku_id": row["sku_id"],
                    "selected_flag": "true",
                    "rank": rank,
                    "score": round(hybrid_score, score_precision),
                    "topk_score": round(topk_score, 6),
                    "structure_score": round(structure_score, 6),
                    "ml_score": "",
                    "source_tag": "hybrid",
                    "selected_k": selected_k,
                    "candidate_sku_count": candidate_count,
                    "cumulative_volume": round(cumulative_volume, 6),
                }
            )

    row_count = write_csv(run_dir / "hybrid_result.csv", HYBRID_RESULT_FIELDS, output_rows)
    return {
        "row_count": row_count,
        "fdc_count": len(selected_counts),
        "min_selected_rows": min(selected_counts.values()) if selected_counts else 0,
        "max_selected_rows": max(selected_counts.values()) if selected_counts else 0,
        "total_selected_rows": sum(selected_counts.values()),
        "topk_weight": topk_weight,
        "reverse_weight": reverse_weight,
        "topk_overlap_rows": sum(topk_overlap_counts.values()),
        "reverse_overlap_rows": sum(reverse_overlap_counts.values()),
        "avg_topk_overlap_ratio": round(
            sum(topk_overlap_counts.values()) / sum(selected_counts.values()),
            6,
        )
        if selected_counts and sum(selected_counts.values()) > 0
        else 0,
        "avg_reverse_overlap_ratio": round(
            sum(reverse_overlap_counts.values()) / sum(selected_counts.values()),
            6,
        )
        if selected_counts and sum(selected_counts.values()) > 0
        else 0,
    }
