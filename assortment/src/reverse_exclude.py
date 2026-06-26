"""Reverse-Exclude assortment method based on historical order baskets."""

from __future__ import annotations

import csv
import heapq
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterator

from assortment.src.common import as_bool, as_date_str, as_float, as_int, write_csv


REVERSE_EXCLUDE_RESULT_FIELDS = [
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


def _iter_order_baskets(
    orders_path: Path,
    order_items_path: Path,
) -> Iterator[tuple[dict[str, str], list[dict[str, str]]]]:
    with orders_path.open("r", encoding="utf-8", newline="") as orders_file, order_items_path.open(
        "r", encoding="utf-8", newline=""
    ) as items_file:
        orders = csv.DictReader(orders_file)
        items = csv.DictReader(items_file)
        current_item = next(items, None)
        for order in orders:
            order_id = order["order_id"]
            basket = []
            while current_item is not None and current_item["order_id"] == order_id:
                basket.append(current_item)
                current_item = next(items, None)
            yield order, basket


def _load_historical_baskets(
    config: dict[str, Any],
    candidate_by_fdc: dict[str, list[dict[str, str]]],
    k_by_fdc: dict[str, dict[str, str]],
) -> tuple[dict[str, Counter[tuple[str, ...]]], dict[str, int]]:
    candidate_sets = {
        fdc_id: {row["sku_id"] for row in rows}
        for fdc_id, rows in candidate_by_fdc.items()
    }
    historical_start_by_fdc = {
        fdc_id: row["historical_window_start"]
        for fdc_id, row in k_by_fdc.items()
    }
    historical_end_by_fdc = {
        fdc_id: row["historical_window_end"]
        for fdc_id, row in k_by_fdc.items()
    }
    reverse_cfg = config["reverse_exclude"]
    include_single = bool(reverse_cfg.get("include_single_item_orders", True))
    max_order_sku_count = as_int(reverse_cfg.get("max_order_sku_count", 20), 20)

    baskets: dict[str, Counter[tuple[str, ...]]] = defaultdict(Counter)
    stats = Counter()
    for order, item_rows in _iter_order_baskets(Path(config["inputs"]["orders"]), Path(config["inputs"]["order_items"])):
        fdc_id = order["fdc_id"]
        candidate_set = candidate_sets.get(fdc_id)
        if candidate_set is None:
            continue
        order_date = order["order_date"]
        if order_date < historical_start_by_fdc[fdc_id] or order_date > historical_end_by_fdc[fdc_id]:
            continue
        sku_ids = tuple(sorted({item["sku_id"] for item in item_rows}))
        if not sku_ids:
            continue
        stats["historical_orders_seen"] += 1
        if len(sku_ids) == 1 and not include_single:
            stats["skipped_single_item_orders"] += 1
            continue
        if len(sku_ids) > max_order_sku_count:
            stats["skipped_large_baskets"] += 1
            continue
        if any(sku_id not in candidate_set for sku_id in sku_ids):
            stats["skipped_non_candidate_baskets"] += 1
            continue
        baskets[fdc_id][sku_ids] += 1
        stats["usable_historical_orders"] += 1
    return baskets, dict(stats)


def _reverse_exclude_one_fdc(
    candidates: list[dict[str, str]],
    selected_k: int,
    basket_counter: Counter[tuple[str, ...]],
    min_order_count: int,
) -> tuple[list[dict[str, str]], dict[str, int]]:
    candidate_by_sku = {row["sku_id"]: row for row in candidates}
    active_skus = set(candidate_by_sku)
    baskets: list[tuple[tuple[str, ...], int]] = [
        (sku_ids, count)
        for sku_ids, count in basket_counter.items()
        if count >= min_order_count
    ]
    active_basket = [True] * len(baskets)
    sku_to_baskets: dict[str, list[int]] = defaultdict(list)
    influence: dict[str, int] = {sku_id: 0 for sku_id in active_skus}

    for basket_index, (sku_ids, count) in enumerate(baskets):
        for sku_id in sku_ids:
            sku_to_baskets[sku_id].append(basket_index)
            influence[sku_id] += count

    heap: list[tuple[int, int, float, float, str]] = []
    for sku_id, row in candidate_by_sku.items():
        heapq.heappush(
            heap,
            (
                influence[sku_id],
                as_int(row["historical_order_count"]),
                as_float(row["future_promo_score"]),
                as_float(row["static_priority_score"]),
                sku_id,
            ),
        )

    removed_count = 0
    invalidated_basket_count = 0
    invalidated_order_count = 0
    while len(active_skus) > selected_k and heap:
        current_influence, _, _, _, sku_id = heapq.heappop(heap)
        if sku_id not in active_skus:
            continue
        if current_influence != influence[sku_id]:
            row = candidate_by_sku[sku_id]
            heapq.heappush(
                heap,
                (
                    influence[sku_id],
                    as_int(row["historical_order_count"]),
                    as_float(row["future_promo_score"]),
                    as_float(row["static_priority_score"]),
                    sku_id,
                ),
            )
            continue

        active_skus.remove(sku_id)
        removed_count += 1
        for basket_index in sku_to_baskets.get(sku_id, []):
            if not active_basket[basket_index]:
                continue
            active_basket[basket_index] = False
            invalidated_basket_count += 1
            basket_skus, order_count = baskets[basket_index]
            invalidated_order_count += order_count
            for other_sku in basket_skus:
                if other_sku == sku_id or other_sku not in active_skus:
                    continue
                influence[other_sku] -= order_count
                other_row = candidate_by_sku[other_sku]
                heapq.heappush(
                    heap,
                    (
                        influence[other_sku],
                        as_int(other_row["historical_order_count"]),
                        as_float(other_row["future_promo_score"]),
                        as_float(other_row["static_priority_score"]),
                        other_sku,
                    ),
                )

    selected = [candidate_by_sku[sku_id] for sku_id in active_skus]
    selected.sort(
        key=lambda row: (
            -influence[row["sku_id"]],
            -as_int(row["historical_order_count"]),
            -as_float(row["future_promo_score"]),
            -as_float(row["static_priority_score"]),
            row["sku_id"],
        )
    )
    summary = {
        "candidate_count": len(candidates),
        "selected_count": len(selected),
        "removed_count": removed_count,
        "usable_basket_types": len(baskets),
        "active_basket_types": sum(1 for flag in active_basket if flag),
        "invalidated_basket_types": invalidated_basket_count,
        "usable_order_count": sum(count for _, count in baskets),
        "active_order_count": sum(count for index, (_, count) in enumerate(baskets) if active_basket[index]),
        "invalidated_order_count": invalidated_order_count,
    }
    for row in selected:
        row["_reverse_influence"] = str(influence[row["sku_id"]])
    return selected, summary


def build_reverse_exclude_result(config: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    reverse_cfg = config["reverse_exclude"]
    candidate_by_fdc = _load_candidate_rows(run_dir / "candidate_pool.csv")
    k_by_fdc = _load_k_table(run_dir / "k_table.csv")
    basket_by_fdc, basket_load_stats = _load_historical_baskets(config, candidate_by_fdc, k_by_fdc)

    output_rows: list[dict[str, Any]] = []
    fdc_summaries: dict[str, dict[str, int]] = {}
    anchor_date = as_date_str(config["anchor_date"])
    effective_start_date = as_date_str(config["effective_start_date"])
    effective_end_date = as_date_str(config["effective_end_date"])
    method_version = reverse_cfg["method_version"]
    assortment_version = reverse_cfg["assortment_version"]
    min_order_count = as_int(reverse_cfg.get("min_order_count", 1), 1)

    for fdc_id in sorted(candidate_by_fdc):
        candidates = candidate_by_fdc[fdc_id]
        k_row = k_by_fdc[fdc_id]
        selected_k = as_int(k_row["selected_k"])
        candidate_count = as_int(k_row["candidate_sku_count"])
        selected, summary = _reverse_exclude_one_fdc(
            candidates,
            selected_k,
            basket_by_fdc.get(fdc_id, Counter()),
            min_order_count,
        )
        cumulative_volume = 0.0
        for rank, row in enumerate(selected, start=1):
            structure_score = as_float(row["_reverse_influence"])
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
                    "score": round(structure_score, 6),
                    "topk_score": row["historical_order_count"],
                    "structure_score": round(structure_score, 6),
                    "ml_score": "",
                    "source_tag": "reverse_exclude",
                    "selected_k": selected_k,
                    "candidate_sku_count": candidate_count,
                    "cumulative_volume": round(cumulative_volume, 6),
                }
            )
        fdc_summaries[fdc_id] = summary

    row_count = write_csv(run_dir / "reverse_exclude_result.csv", REVERSE_EXCLUDE_RESULT_FIELDS, output_rows)
    selected_counts = [summary["selected_count"] for summary in fdc_summaries.values()]
    return {
        "row_count": row_count,
        "fdc_count": len(fdc_summaries),
        "min_selected_rows": min(selected_counts) if selected_counts else 0,
        "max_selected_rows": max(selected_counts) if selected_counts else 0,
        "total_selected_rows": sum(selected_counts),
        "basket_load_stats": basket_load_stats,
        "total_usable_basket_types": sum(summary["usable_basket_types"] for summary in fdc_summaries.values()),
        "total_active_basket_types": sum(summary["active_basket_types"] for summary in fdc_summaries.values()),
        "total_usable_order_count": sum(summary["usable_order_count"] for summary in fdc_summaries.values()),
        "total_active_order_count": sum(summary["active_order_count"] for summary in fdc_summaries.values()),
        "fdc_summaries": fdc_summaries,
    }
