"""Evaluation utilities for assortment experiment outputs."""

from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from assortment.src.common import as_bool, as_date_str, as_float, as_int


RESULT_FILES = {
    "topk": "topk_result.csv",
    "reverse_exclude": "reverse_exclude_result.csv",
    "hybrid": "hybrid_result.csv",
    "ml_topk": "ml_topk_result.csv",
}


@dataclass(frozen=True)
class OrderBasket:
    order_id: str
    order_date: str
    fdc_id: str
    sku_ids: tuple[str, ...]
    category_ids: tuple[str, ...]
    size_bucket: str


@dataclass
class AssortmentMethod:
    name: str
    method_version: str
    assortment_version: str
    selected_by_fdc: dict[str, list[str]]
    selected_sets: dict[str, set[str]]
    selected_count_by_fdc: dict[str, int]
    candidate_count_by_fdc: dict[str, int]
    metadata: dict[str, str]


def _is_lfs_pointer(path: Path) -> bool:
    if not path.exists():
        return False
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        first_line = f.readline().strip()
    return first_line == "version https://git-lfs.github.com/spec/v1"


def _ensure_csv_fields(path: Path, required: set[str]) -> None:
    if _is_lfs_pointer(path):
        raise ValueError(f"{path} is a Git LFS pointer, not a materialized CSV file")
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = set(reader.fieldnames or [])
    missing = sorted(required - fieldnames)
    if missing:
        raise ValueError(f"{path} missing required fields: {missing}")


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _size_bucket(size: int) -> str:
    if size <= 1:
        return "size_1"
    if size == 2:
        return "size_2"
    return "size_3_plus"


def load_candidate_pool(path: Path) -> tuple[set[tuple[str, str]], dict[str, int], dict[str, str], dict[str, bool]]:
    _ensure_csv_fields(path, {"fdc_id", "sku_id", "candidate_flag", "category_id", "is_regular_product"})
    candidate_pairs: set[tuple[str, str]] = set()
    candidate_count_by_fdc: dict[str, int] = defaultdict(int)
    category_by_sku: dict[str, str] = {}
    regular_by_sku: dict[str, bool] = {}
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            category_by_sku.setdefault(row["sku_id"], row["category_id"])
            regular_by_sku.setdefault(row["sku_id"], as_bool(row["is_regular_product"]))
            if as_bool(row["candidate_flag"]):
                candidate_pairs.add((row["fdc_id"], row["sku_id"]))
                candidate_count_by_fdc[row["fdc_id"]] += 1
    return candidate_pairs, dict(candidate_count_by_fdc), category_by_sku, regular_by_sku


def load_sku_metadata(
    sku_master_path: Path | None,
    category_by_sku: dict[str, str],
    regular_by_sku: dict[str, bool],
) -> tuple[dict[str, str], dict[str, bool]]:
    if sku_master_path is None or not sku_master_path.exists() or _is_lfs_pointer(sku_master_path):
        return category_by_sku, regular_by_sku
    _ensure_csv_fields(sku_master_path, {"sku_id", "category_id", "is_regular_product"})
    categories = dict(category_by_sku)
    regular = dict(regular_by_sku)
    with sku_master_path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            categories[row["sku_id"]] = row["category_id"]
            regular[row["sku_id"]] = as_bool(row["is_regular_product"])
    return categories, regular


def iter_order_baskets(orders_path: Path, order_items_path: Path) -> Iterable[tuple[dict[str, str], list[dict[str, str]]]]:
    _ensure_csv_fields(orders_path, {"order_id", "order_date", "fdc_id"})
    _ensure_csv_fields(order_items_path, {"order_id", "sku_id"})
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


def load_regular_order_baskets(
    orders_path: Path,
    order_items_path: Path,
    evaluation_start_date: str,
    evaluation_end_date: str,
    category_by_sku: dict[str, str],
    regular_by_sku: dict[str, bool],
) -> list[OrderBasket]:
    baskets: list[OrderBasket] = []
    for order, item_rows in iter_order_baskets(orders_path, order_items_path):
        order_date = order["order_date"]
        if order_date < evaluation_start_date or order_date > evaluation_end_date:
            continue
        sku_ids = tuple(sorted({row["sku_id"] for row in item_rows}))
        if not sku_ids:
            continue
        if not all(regular_by_sku.get(sku_id, True) for sku_id in sku_ids):
            continue
        categories = tuple(sorted({category_by_sku.get(sku_id, "UNKNOWN") for sku_id in sku_ids}))
        baskets.append(
            OrderBasket(
                order_id=order["order_id"],
                order_date=order_date,
                fdc_id=order["fdc_id"],
                sku_ids=sku_ids,
                category_ids=categories,
                size_bucket=_size_bucket(len(sku_ids)),
            )
        )
    return baskets


def load_assortment_method(name: str, path: Path) -> AssortmentMethod:
    _ensure_csv_fields(
        path,
        {
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
            "sku_id",
            "selected_flag",
            "rank",
            "candidate_sku_count",
        },
    )
    ranked_by_fdc: dict[str, list[tuple[int, str]]] = defaultdict(list)
    selected_count_by_fdc: dict[str, int] = defaultdict(int)
    candidate_count_by_fdc: dict[str, int] = {}
    metadata: dict[str, str] = {}

    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if not metadata:
                metadata = {
                    "experiment_id": row["experiment_id"],
                    "data_version": row["data_version"],
                    "candidate_pool_version": row["candidate_pool_version"],
                    "k_rule_version": row["k_rule_version"],
                    "method_version": row["method_version"],
                    "assortment_version": row["assortment_version"],
                    "anchor_date": row["anchor_date"],
                    "effective_start_date": row["effective_start_date"],
                    "effective_end_date": row["effective_end_date"],
                }
            candidate_count_by_fdc[row["fdc_id"]] = as_int(row["candidate_sku_count"])
            if not as_bool(row["selected_flag"]):
                continue
            rank = as_int(row["rank"])
            ranked_by_fdc[row["fdc_id"]].append((rank, row["sku_id"]))
            selected_count_by_fdc[row["fdc_id"]] += 1

    selected_by_fdc = {
        fdc_id: [sku_id for _rank, sku_id in sorted(values)]
        for fdc_id, values in ranked_by_fdc.items()
    }
    return AssortmentMethod(
        name=name,
        method_version=metadata.get("method_version", ""),
        assortment_version=metadata.get("assortment_version", ""),
        selected_by_fdc=selected_by_fdc,
        selected_sets={fdc_id: set(sku_ids) for fdc_id, sku_ids in selected_by_fdc.items()},
        selected_count_by_fdc=dict(selected_count_by_fdc),
        candidate_count_by_fdc=candidate_count_by_fdc,
        metadata=metadata,
    )


def build_future_frequency(orders: Iterable[OrderBasket]) -> tuple[Counter[tuple[str, str]], dict[str, Counter[str]]]:
    future_frequency: Counter[tuple[str, str]] = Counter()
    by_fdc: dict[str, Counter[str]] = defaultdict(Counter)
    for order in orders:
        for sku_id in order.sku_ids:
            future_frequency[(order.fdc_id, sku_id)] += 1
            by_fdc[order.fdc_id][sku_id] += 1
    return future_frequency, by_fdc


def ndcg_at_k(ranked_skus: list[str], relevance_by_sku: Counter[str]) -> float:
    if not ranked_skus:
        return 0.0
    dcg = 0.0
    for index, sku_id in enumerate(ranked_skus, start=1):
        dcg += relevance_by_sku.get(sku_id, 0) / math.log2(index + 1)
    ideal_relevance = sorted(relevance_by_sku.values(), reverse=True)[: len(ranked_skus)]
    idcg = sum(value / math.log2(index + 1) for index, value in enumerate(ideal_relevance, start=1))
    return _safe_ratio(dcg, idcg)


def _order_stats_payload(total: int, covered: int) -> dict[str, Any]:
    return {
        "regular_order_count": total,
        "covered_regular_order_count": covered,
        "local_order_fulfillment_rate": round(_safe_ratio(covered, total), 8),
    }


def evaluate_method(
    method: AssortmentMethod,
    orders: list[OrderBasket],
    candidate_pairs: set[tuple[str, str]],
    candidate_count_by_fdc: dict[str, int],
    future_frequency: Counter[tuple[str, str]],
    future_frequency_by_fdc: dict[str, Counter[str]],
) -> dict[str, Any]:
    total_orders = 0
    covered_orders = 0
    order_stats_by_fdc: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    order_stats_by_size: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    order_stats_by_category: dict[str, list[int]] = defaultdict(lambda: [0, 0])

    for order in orders:
        selected = method.selected_sets.get(order.fdc_id, set())
        covered = all(sku_id in selected for sku_id in order.sku_ids)
        total_orders += 1
        if covered:
            covered_orders += 1
        order_stats_by_fdc[order.fdc_id][0] += 1
        order_stats_by_fdc[order.fdc_id][1] += int(covered)
        order_stats_by_size[order.size_bucket][0] += 1
        order_stats_by_size[order.size_bucket][1] += int(covered)
        for category_id in order.category_ids:
            order_stats_by_category[category_id][0] += 1
            order_stats_by_category[category_id][1] += int(covered)

    total_future_frequency = sum(future_frequency.values())
    selected_future_frequency = sum(
        count
        for (fdc_id, sku_id), count in future_frequency.items()
        if sku_id in method.selected_sets.get(fdc_id, set())
    )
    future_pairs = set(future_frequency)
    candidate_hits = sum(1 for key in future_pairs if key in candidate_pairs)

    ndcg_weighted_sum = 0.0
    ndcg_weight = 0
    for fdc_id, ranked_skus in method.selected_by_fdc.items():
        relevance = future_frequency_by_fdc.get(fdc_id, Counter())
        weight = sum(relevance.values())
        if weight <= 0:
            continue
        ndcg_weighted_sum += ndcg_at_k(ranked_skus, relevance) * weight
        ndcg_weight += weight

    selected_count = sum(method.selected_count_by_fdc.values())
    candidate_count = sum(candidate_count_by_fdc.get(fdc_id, count) for fdc_id, count in method.candidate_count_by_fdc.items())
    fdc_count = len(method.selected_by_fdc)

    overall = {
        **_order_stats_payload(total_orders, covered_orders),
        "fdc_count": fdc_count,
        "selected_sku_count": selected_count,
        "candidate_sku_count": candidate_count,
        "sku_frequency_recall_at_k": round(_safe_ratio(selected_future_frequency, total_future_frequency), 8),
        "ndcg_at_k": round(_safe_ratio(ndcg_weighted_sum, ndcg_weight), 8),
        "candidate_hit_rate": round(_safe_ratio(candidate_hits, len(future_pairs)), 8),
        "avg_selected_k": round(_safe_ratio(selected_count, fdc_count), 6),
        "avg_candidate_count": round(_safe_ratio(candidate_count, fdc_count), 6),
    }

    by_fdc: dict[str, dict[str, Any]] = {}
    for fdc_id in sorted(set(order_stats_by_fdc) | set(method.selected_by_fdc)):
        total, covered = order_stats_by_fdc.get(fdc_id, [0, 0])
        relevance = future_frequency_by_fdc.get(fdc_id, Counter())
        selected_set = method.selected_sets.get(fdc_id, set())
        selected_frequency = sum(count for sku_id, count in relevance.items() if sku_id in selected_set)
        future_pair_count = len(relevance)
        candidate_hit_count = sum(1 for sku_id in relevance if (fdc_id, sku_id) in candidate_pairs)
        by_fdc[fdc_id] = {
            **_order_stats_payload(total, covered),
            "selected_sku_count": method.selected_count_by_fdc.get(fdc_id, 0),
            "candidate_sku_count": candidate_count_by_fdc.get(fdc_id, method.candidate_count_by_fdc.get(fdc_id, 0)),
            "sku_frequency_recall_at_k": round(_safe_ratio(selected_frequency, sum(relevance.values())), 8),
            "ndcg_at_k": round(ndcg_at_k(method.selected_by_fdc.get(fdc_id, []), relevance), 8),
            "candidate_hit_rate": round(_safe_ratio(candidate_hit_count, future_pair_count), 8),
        }

    return {
        "method_version": method.method_version,
        "assortment_version": method.assortment_version,
        "overall": overall,
        "by_fdc": by_fdc,
        "coverage_by_order_size": {
            bucket: _order_stats_payload(values[0], values[1])
            for bucket, values in sorted(order_stats_by_size.items())
        },
        "coverage_by_category": {
            category_id: _order_stats_payload(values[0], values[1])
            for category_id, values in sorted(order_stats_by_category.items())
        },
    }


def build_metric_rows(
    config: dict[str, Any],
    method: AssortmentMethod,
    method_metrics: dict[str, Any],
    evaluation_split: str,
    evaluation_start_date: str,
    evaluation_end_date: str,
) -> list[dict[str, Any]]:
    base = {
        "experiment_id": config["experiment_id"],
        "data_version": config["data_version"],
        "candidate_pool_version": config["candidate_pool_version"],
        "k_rule_version": config["k_rule_version"],
        "method_version": method.method_version,
        "assortment_version": method.assortment_version,
        "anchor_date": as_date_str(config["anchor_date"]),
        "effective_start_date": as_date_str(config["effective_start_date"]),
        "effective_end_date": as_date_str(config["effective_end_date"]),
        "evaluation_split": evaluation_split,
        "evaluation_start_date": evaluation_start_date,
        "evaluation_end_date": evaluation_end_date,
    }
    rows = []
    overall = method_metrics["overall"]
    rows.append({**base, **overall, "metric_level": "overall", "metric_key": "ALL"})
    for fdc_id, metrics in method_metrics["by_fdc"].items():
        rows.append(
            {
                **base,
                **metrics,
                "metric_level": "fdc",
                "metric_key": fdc_id,
                "fdc_count": 1,
                "avg_selected_k": metrics["selected_sku_count"],
                "avg_candidate_count": metrics["candidate_sku_count"],
            }
        )
    return rows


def write_report(report_path: Path, summary: dict[str, Any]) -> None:
    lines = [
        f"# Assortment Report: {summary['experiment_id']}",
        "",
        f"- data_version: {summary['data_version']}",
        f"- evaluation_split: {summary['evaluation_split']}",
        f"- evaluation_window: {summary['evaluation_start_date']} to {summary['evaluation_end_date']}",
        f"- regular_order_count: {summary['regular_order_count']}",
        "",
        "## Method Comparison",
        "",
        "| method | local_order_fulfillment_rate | sku_frequency_recall_at_k | ndcg_at_k | candidate_hit_rate |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in summary["comparison"]:
        lines.append(
            "| {method} | {local_order_fulfillment_rate:.8f} | {sku_frequency_recall_at_k:.8f} | "
            "{ndcg_at_k:.8f} | {candidate_hit_rate:.8f} |".format(**row)
        )
    lines.extend(["", "## Outputs", "", "```json", json.dumps(summary["outputs"], ensure_ascii=False, indent=2), "```", ""])
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")


def evaluate_assortment(config: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    evaluation_cfg = config.get("evaluation", {}) or {}
    evaluation_split = str(evaluation_cfg.get("evaluation_split", "test"))
    evaluation_start_date = str(evaluation_cfg.get("evaluation_start_date", config["effective_start_date"]))
    evaluation_end_date = str(evaluation_cfg.get("evaluation_end_date", config["effective_end_date"]))
    method_names = list(evaluation_cfg.get("methods", RESULT_FILES.keys()))

    candidate_pairs, candidate_count_by_fdc, category_by_sku, regular_by_sku = load_candidate_pool(run_dir / "candidate_pool.csv")
    sku_master_value = config.get("inputs", {}).get("sku_master")
    category_by_sku, regular_by_sku = load_sku_metadata(
        Path(sku_master_value) if sku_master_value else None,
        category_by_sku,
        regular_by_sku,
    )
    orders = load_regular_order_baskets(
        Path(config["inputs"]["orders"]),
        Path(config["inputs"]["order_items"]),
        evaluation_start_date,
        evaluation_end_date,
        category_by_sku,
        regular_by_sku,
    )
    future_frequency, future_frequency_by_fdc = build_future_frequency(orders)

    methods = [
        load_assortment_method(name, run_dir / RESULT_FILES[name])
        for name in method_names
        if name in RESULT_FILES and (run_dir / RESULT_FILES[name]).exists()
    ]
    method_metrics = {
        method.name: evaluate_method(
            method,
            orders,
            candidate_pairs,
            candidate_count_by_fdc,
            future_frequency,
            future_frequency_by_fdc,
        )
        for method in methods
    }
    metric_rows = [
        row
        for method in methods
        for row in build_metric_rows(
            config,
            method,
            method_metrics[method.name],
            evaluation_split,
            evaluation_start_date,
            evaluation_end_date,
        )
    ]
    comparison = sorted(
        [
            {
                "method": method_name,
                "assortment_version": metrics["assortment_version"],
                **metrics["overall"],
            }
            for method_name, metrics in method_metrics.items()
        ],
        key=lambda row: (
            -as_float(row["local_order_fulfillment_rate"]),
            -as_float(row["sku_frequency_recall_at_k"]),
            row["method"],
        ),
    )
    metrics_path = run_dir / "assortment_metrics.json"
    report_dir = Path(str(evaluation_cfg.get("report_dir", "assortment/reports")))
    report_path = report_dir / f"{config['experiment_id']}_assortment_report.md"
    summary = {
        "experiment_id": config["experiment_id"],
        "data_version": config["data_version"],
        "candidate_pool_version": config["candidate_pool_version"],
        "k_rule_version": config["k_rule_version"],
        "anchor_date": as_date_str(config["anchor_date"]),
        "effective_start_date": as_date_str(config["effective_start_date"]),
        "effective_end_date": as_date_str(config["effective_end_date"]),
        "evaluation_split": evaluation_split,
        "evaluation_start_date": evaluation_start_date,
        "evaluation_end_date": evaluation_end_date,
        "regular_order_count": len(orders),
        "future_sku_frequency_total": sum(future_frequency.values()),
        "methods": method_metrics,
        "metric_rows": metric_rows,
        "comparison": comparison,
        "outputs": {
            "assortment_metrics": str(metrics_path),
            "assortment_report": str(report_path),
        },
    }
    metrics_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_report(report_path, summary)
    return summary
