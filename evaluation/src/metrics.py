"""Metric normalization helpers for evaluation runs."""

from __future__ import annotations

from typing import Any

from evaluation.src.common import to_text


METRIC_FIELDS = [
    "evaluation_id",
    "stage",
    "experiment_id",
    "run_status",
    "method_name",
    "method_family",
    "data_version",
    "split_version",
    "candidate_pool_version",
    "k_rule_version",
    "assortment_version",
    "inventory_version",
    "simulation_rule_version",
    "cost_config_version",
    "policy_version",
    "model_version",
    "evaluation_split",
    "evaluation_start_date",
    "evaluation_end_date",
    "metric_level",
    "metric_key",
    "metric_name",
    "metric_value",
    "metric_unit",
    "metric_type",
    "source_path",
    "notes",
]


RATIO_METRICS = {
    "local_order_fulfillment_rate",
    "sku_frequency_recall_at_k",
    "ndcg_at_k",
    "candidate_hit_rate",
    "fdc_fulfillment_rate",
    "loss_ratio",
    "stockout_rate",
}

COST_METRICS = {
    "transfer_cost",
    "rdc_fallback_cost",
    "lost_sales_cost",
    "holding_cost",
    "total_cost",
}

DEMAND_METRICS = {
    "total_demand_qty",
    "fdc_fulfilled_qty",
    "rdc_fallback_qty",
    "lost_sales_qty",
}


def metric_unit(metric_name: str) -> str:
    if metric_name in RATIO_METRICS:
        return "ratio"
    if metric_name in COST_METRICS:
        return "cost"
    if metric_name in DEMAND_METRICS or metric_name.endswith("_qty"):
        return "qty"
    if metric_name.endswith("_rows") or metric_name.endswith("_count") or metric_name.startswith("num_"):
        return "count"
    return "value"


def metric_type(metric_name: str) -> str:
    if metric_name in RATIO_METRICS:
        return "service"
    if metric_name in COST_METRICS:
        return "cost"
    if metric_name in DEMAND_METRICS:
        return "demand"
    if metric_name.startswith("validation_"):
        return "quality"
    if metric_name.startswith("num_") or metric_name.endswith("_rows") or metric_name.endswith("_count"):
        return "volume"
    return "operational"


def base_metric_context(config: dict[str, Any]) -> dict[str, Any]:
    versions = config.get("versions", {})
    window = config["evaluation_window"]
    return {
        "evaluation_id": config["evaluation_id"],
        "data_version": config["data_version"],
        "split_version": config["split_version"],
        "candidate_pool_version": versions.get("candidate_pool_version", ""),
        "k_rule_version": versions.get("k_rule_version", ""),
        "assortment_version": versions.get("assortment_version", ""),
        "inventory_version": versions.get("inventory_version", ""),
        "simulation_rule_version": versions.get("simulation_rule_version", ""),
        "cost_config_version": versions.get("cost_config_version", ""),
        "policy_version": "",
        "model_version": "",
        "evaluation_split": config["evaluation_split"],
        "evaluation_start_date": to_text(window["start_date"]),
        "evaluation_end_date": to_text(window["end_date"]),
    }


def metric_row(
    config: dict[str, Any],
    stage: str,
    experiment_id: str,
    metric_name: str,
    metric_value: Any,
    *,
    run_status: str = "available",
    method_name: str = "",
    method_family: str = "",
    metric_level: str = "overall",
    metric_key: str = "ALL",
    source_path: str = "",
    notes: str = "",
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = {
        **base_metric_context(config),
        "stage": stage,
        "experiment_id": experiment_id,
        "run_status": run_status,
        "method_name": method_name,
        "method_family": method_family,
        "metric_level": metric_level,
        "metric_key": metric_key,
        "metric_name": metric_name,
        "metric_value": metric_value,
        "metric_unit": metric_unit(metric_name),
        "metric_type": metric_type(metric_name),
        "source_path": source_path,
        "notes": notes,
    }
    if overrides:
        row.update({key: to_text(value) for key, value in overrides.items()})
    return row

