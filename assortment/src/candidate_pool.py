"""Build FDC-SKU candidate pools for assortment selection."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Any

from assortment.src.common import as_bool, as_date_str, as_float, as_int, write_csv


CANDIDATE_POOL_FIELDS = [
    "experiment_id",
    "data_version",
    "candidate_pool_version",
    "anchor_date",
    "effective_start_date",
    "effective_end_date",
    "fdc_id",
    "rdc_id",
    "sku_id",
    "eligible_flag",
    "candidate_flag",
    "filter_reason",
    "recall_source",
    "category_id",
    "brand_id",
    "temperature_zone",
    "price",
    "volume",
    "weight",
    "is_regular_product",
    "historical_demand_qty",
    "historical_order_count",
    "active_demand_days",
    "planned_promo_flag",
    "future_promo_score",
    "static_priority_score",
]


def _load_anchor_features(path: Path, anchor_date: str) -> dict[tuple[str, str], dict[str, str]]:
    features: dict[tuple[str, str], dict[str, str]] = {}
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row["anchor_date"] != anchor_date:
                continue
            features[(row["fdc_id"], row["sku_id"])] = row
    return features


def _load_candidate_base(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _load_order_type_counts(path: Path) -> dict[str, tuple[str, int, int]]:
    counts: dict[str, tuple[str, int, int]] = {}
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            counts[row["order_type_id"]] = (
                row["fdc_id"],
                as_int(row["sku_count"]),
                as_int(row["order_count"]),
            )
    return counts


def _load_co_purchase_counts(order_type_table: Path, order_type_items: Path) -> dict[tuple[str, str], int]:
    type_counts = _load_order_type_counts(order_type_table)
    sku_counts: dict[tuple[str, str], int] = defaultdict(int)
    with order_type_items.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            fdc_id, sku_count, order_count = type_counts[row["order_type_id"]]
            if sku_count <= 1:
                continue
            sku_counts[(fdc_id, row["sku_id"])] += order_count
    return sku_counts


def _top_n_by_fdc(
    rows: list[dict[str, str]],
    value_by_key: dict[tuple[str, str], float],
    n: int,
) -> set[tuple[str, str]]:
    if n <= 0:
        return set()
    grouped: dict[str, list[tuple[float, str]]] = defaultdict(list)
    for row in rows:
        key = (row["fdc_id"], row["sku_id"])
        grouped[row["fdc_id"]].append((value_by_key.get(key, 0.0), row["sku_id"]))
    selected: set[tuple[str, str]] = set()
    for fdc_id, values in grouped.items():
        values.sort(key=lambda item: (-item[0], item[1]))
        for value, sku_id in values[:n]:
            if value > 0:
                selected.add((fdc_id, sku_id))
    return selected


def build_candidate_pool(config: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    candidate_cfg = config["candidate_pool"]
    inputs = config["inputs"]
    anchor_date = as_date_str(config["anchor_date"])
    effective_start_date = as_date_str(config["effective_start_date"])
    effective_end_date = as_date_str(config["effective_end_date"])

    base_rows = _load_candidate_base(Path(inputs["candidate_pool_base"]))
    features = _load_anchor_features(Path(inputs["ml_topk_features"]), anchor_date)
    co_purchase_counts = _load_co_purchase_counts(
        Path(inputs["order_type_table"]),
        Path(inputs["order_type_items"]),
    )

    base_popularity_by_key = {
        (row["fdc_id"], row["sku_id"]): as_float(row["base_popularity"])
        for row in base_rows
    }
    strategic_keys = _top_n_by_fdc(
        base_rows,
        base_popularity_by_key,
        as_int(candidate_cfg["strategic_top_n_per_fdc"]),
    )
    co_purchase_keys = _top_n_by_fdc(
        base_rows,
        {key: float(value) for key, value in co_purchase_counts.items()},
        as_int(candidate_cfg["co_purchase_top_n_per_fdc"]),
    )

    history_order_field = candidate_cfg["history_order_field"]
    history_demand_field = candidate_cfg["history_demand_field"]
    active_days_field = candidate_cfg["active_days_field"]
    future_promo_days_field = candidate_cfg["future_promo_days_field"]
    future_campaign_days_field = candidate_cfg["future_campaign_days_field"]

    output_rows: list[dict[str, Any]] = []
    recall_counts: dict[str, int] = defaultdict(int)
    filter_counts: dict[str, int] = defaultdict(int)

    for row in base_rows:
        key = (row["fdc_id"], row["sku_id"])
        feature = features.get(key, {})
        historical_order_count = as_int(feature.get(history_order_field), as_int(row["demand_order_count"]))
        historical_demand_qty = as_int(feature.get(history_demand_field), as_int(row["total_demand_qty"]))
        active_demand_days = as_int(feature.get(active_days_field), as_int(row["active_demand_days"]))
        future_promo_days = as_int(feature.get(future_promo_days_field))
        future_campaign_days = as_int(feature.get(future_campaign_days_field))
        future_promo_score = (
            future_promo_days * as_float(candidate_cfg["future_promo_day_weight"])
            + future_campaign_days * as_float(candidate_cfg["future_campaign_day_weight"])
        )
        planned_promo_flag = future_promo_days > 0
        is_regular = as_bool(row["is_regular_product"])
        eligible = as_bool(row["eligible_flag"])
        base_popularity = as_float(row["base_popularity"])

        is_strategic = key in strategic_keys
        is_co_purchase = key in co_purchase_keys
        is_new_product = (
            active_demand_days <= as_int(candidate_cfg["new_product_active_days_threshold"])
            and base_popularity >= as_float(candidate_cfg["new_product_min_base_popularity"])
        )
        has_history = historical_order_count >= as_int(candidate_cfg["min_historical_orders"])
        has_priority_signal = planned_promo_flag or is_strategic or is_co_purchase or is_new_product

        candidate_flag = eligible and (has_history or has_priority_signal)
        filter_reason = ""
        if not eligible:
            candidate_flag = False
            filter_reason = "ineligible"
        elif candidate_cfg.get("filter_non_regular", True) and not is_regular:
            if not (candidate_cfg.get("include_priority_non_regular", False) and has_priority_signal):
                candidate_flag = False
                filter_reason = "non_regular"
        elif not candidate_flag:
            filter_reason = "no_historical_or_priority_signal"

        if planned_promo_flag:
            recall_source = "promotion"
        elif is_co_purchase:
            recall_source = "co_purchase"
        elif is_strategic:
            recall_source = "strategic"
        elif is_new_product:
            recall_source = "new_product"
        elif has_history:
            recall_source = "historical_demand"
        else:
            recall_source = "base_pool"

        if candidate_flag:
            recall_counts[recall_source] += 1
        else:
            filter_counts[filter_reason] += 1

        output_rows.append(
            {
                "experiment_id": config["experiment_id"],
                "data_version": config["data_version"],
                "candidate_pool_version": config["candidate_pool_version"],
                "anchor_date": anchor_date,
                "effective_start_date": effective_start_date,
                "effective_end_date": effective_end_date,
                "fdc_id": row["fdc_id"],
                "rdc_id": row["rdc_id"],
                "sku_id": row["sku_id"],
                "eligible_flag": str(eligible).lower(),
                "candidate_flag": str(candidate_flag).lower(),
                "filter_reason": filter_reason,
                "recall_source": recall_source,
                "category_id": row["category_id"],
                "brand_id": row["brand_id"],
                "temperature_zone": row["temperature_zone"],
                "price": row["price"],
                "volume": row["volume"],
                "weight": row["weight"],
                "is_regular_product": str(is_regular).lower(),
                "historical_demand_qty": historical_demand_qty,
                "historical_order_count": historical_order_count,
                "active_demand_days": active_demand_days,
                "planned_promo_flag": str(planned_promo_flag).lower(),
                "future_promo_score": round(future_promo_score, 6),
                "static_priority_score": round(base_popularity, 10),
            }
        )

    row_count = write_csv(run_dir / "candidate_pool.csv", CANDIDATE_POOL_FIELDS, output_rows)
    return {
        "row_count": row_count,
        "candidate_count": sum(1 for row in output_rows if row["candidate_flag"] == "true"),
        "filtered_count": sum(1 for row in output_rows if row["candidate_flag"] != "true"),
        "recall_source_counts": dict(sorted(recall_counts.items())),
        "filter_reason_counts": dict(sorted(filter_counts.items())),
    }
