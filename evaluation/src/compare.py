"""Baseline comparison table construction."""

from __future__ import annotations

from typing import Any

from evaluation.src.common import to_text


COMPARISON_FIELDS = [
    "evaluation_id",
    "comparison_type",
    "comparison_id",
    "run_status",
    "metrics_status",
    "method_name",
    "method_family",
    "assortment_method",
    "inventory_method",
    "expected_assortment_version",
    "observed_assortment_version",
    "expected_inventory_version",
    "observed_inventory_version",
    "source_experiment_id",
    "local_order_fulfillment_rate",
    "sku_frequency_recall_at_k",
    "ndcg_at_k",
    "selected_sku_count",
    "fdc_fulfillment_rate",
    "loss_ratio",
    "lost_sales_qty",
    "transfer_cost",
    "total_cost",
    "notes",
]


def metric_lookup(metrics: list[dict[str, Any]]) -> dict[tuple[str, str, str], str]:
    lookup: dict[tuple[str, str, str], str] = {}
    for row in metrics:
        if row.get("metric_level") != "overall":
            continue
        key = (to_text(row.get("stage")), to_text(row.get("method_name")), to_text(row.get("metric_name")))
        lookup.setdefault(key, to_text(row.get("metric_value")))
    return lookup


def operational_metric(
    values: dict[tuple[str, str, str], str],
    method_name: str,
    metric_name: str,
) -> str:
    return values.get(("inventory", method_name, metric_name), "") or values.get(("simulation", method_name, metric_name), "")


def available_assortment_methods(metrics: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    methods: dict[str, dict[str, str]] = {}
    for row in metrics:
        if row.get("stage") != "assortment":
            continue
        method_name = to_text(row.get("method_name"))
        if not method_name:
            continue
        methods.setdefault(
            method_name,
            {
                "experiment_id": to_text(row.get("experiment_id")),
                "assortment_version": to_text(row.get("assortment_version")),
                "run_status": to_text(row.get("run_status")),
            },
        )
    return methods


def available_inventory_methods(registry: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    methods: dict[str, dict[str, str]] = {}
    for row in registry:
        if row.get("stage") not in {"inventory", "simulation"}:
            continue
        method_name = to_text(row.get("method_name"))
        stage = to_text(row.get("stage"))
        version = to_text(row.get("inventory_version")) if stage == "inventory" else ""
        run_status = to_text(row.get("run_status"))
        if method_name:
            methods[method_name] = {
                "experiment_id": to_text(row.get("experiment_id")),
                "inventory_version": version,
                "run_status": run_status,
                "stage": stage,
            }
        if version and stage == "inventory":
            methods[version] = {
                "experiment_id": to_text(row.get("experiment_id")),
                "inventory_version": version,
                "run_status": run_status,
                "stage": stage,
            }
    return methods


def build_comparison_table(
    config: dict[str, Any],
    registry: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    matrix = config.get("baseline_matrix", {})
    evaluation_id = config["evaluation_id"]
    metric_values = metric_lookup(metrics)
    assortment_available = available_assortment_methods(metrics)
    inventory_available = available_inventory_methods(registry)

    rows: list[dict[str, Any]] = []
    for method in matrix.get("assortment_methods", []):
        name = method["method_name"]
        available = assortment_available.get(name, {})
        status = available.get("run_status", "planned")
        metrics_status = "available" if metric_values.get(("assortment", name, "local_order_fulfillment_rate")) else "partial"
        rows.append(
            {
                "evaluation_id": evaluation_id,
                "comparison_type": "assortment_method",
                "comparison_id": name,
                "run_status": status,
                "metrics_status": metrics_status,
                "method_name": name,
                "method_family": method.get("method_family", ""),
                "assortment_method": name,
                "inventory_method": "",
                "expected_assortment_version": method.get("expected_assortment_version", ""),
                "observed_assortment_version": available.get("assortment_version", ""),
                "expected_inventory_version": "",
                "observed_inventory_version": "",
                "source_experiment_id": available.get("experiment_id", ""),
                "local_order_fulfillment_rate": metric_values.get(("assortment", name, "local_order_fulfillment_rate"), ""),
                "sku_frequency_recall_at_k": metric_values.get(("assortment", name, "sku_frequency_recall_at_k"), ""),
                "ndcg_at_k": metric_values.get(("assortment", name, "ndcg_at_k"), ""),
                "selected_sku_count": metric_values.get(("assortment", name, "total_selected_rows"), "")
                or metric_values.get(("assortment", name, "selected_sku_count"), ""),
                "fdc_fulfillment_rate": "",
                "loss_ratio": "",
                "lost_sales_qty": "",
                "transfer_cost": "",
                "total_cost": "",
                "notes": "assortment evaluation metrics missing" if metrics_status == "partial" else "",
            }
        )

    for method in matrix.get("inventory_methods", []):
        name = method["method_name"]
        expected_version = method.get("expected_inventory_version", "")
        available = inventory_available.get(name) or inventory_available.get(expected_version) or {}
        status = available.get("run_status", "planned")
        metrics_status = "available" if operational_metric(metric_values, name, "fdc_fulfillment_rate") else "missing"
        notes = ""
        if metrics_status == "missing":
            notes = "inventory run or simulation metrics missing"
        elif available.get("stage") == "simulation":
            notes = "using simulation policy metrics as inventory baseline"
        rows.append(
            {
                "evaluation_id": evaluation_id,
                "comparison_type": "inventory_method",
                "comparison_id": name,
                "run_status": status,
                "metrics_status": metrics_status,
                "method_name": name,
                "method_family": method.get("method_family", ""),
                "assortment_method": "",
                "inventory_method": name,
                "expected_assortment_version": "",
                "observed_assortment_version": "",
                "expected_inventory_version": expected_version,
                "observed_inventory_version": available.get("inventory_version", ""),
                "source_experiment_id": available.get("experiment_id", ""),
                "local_order_fulfillment_rate": "",
                "sku_frequency_recall_at_k": "",
                "ndcg_at_k": "",
                "selected_sku_count": "",
                "fdc_fulfillment_rate": operational_metric(metric_values, name, "fdc_fulfillment_rate"),
                "loss_ratio": operational_metric(metric_values, name, "loss_ratio"),
                "lost_sales_qty": operational_metric(metric_values, name, "lost_sales_qty"),
                "transfer_cost": operational_metric(metric_values, name, "transfer_cost"),
                "total_cost": operational_metric(metric_values, name, "total_cost"),
                "notes": notes,
            }
        )

    inventory_by_name = {
        row["method_name"]: row for row in rows if row["comparison_type"] == "inventory_method"
    }
    assortment_by_name = {
        row["method_name"]: row for row in rows if row["comparison_type"] == "assortment_method"
    }
    for combo in matrix.get("combination_experiments", []):
        assortment_method = combo["assortment_method"]
        inventory_method = combo["inventory_method"]
        assortment_row = assortment_by_name.get(assortment_method, {})
        inventory_row = inventory_by_name.get(inventory_method, {})
        assortment_ok = assortment_row.get("run_status") == "available"
        inventory_ok = inventory_row.get("run_status") == "available"
        if assortment_ok and inventory_ok:
            status = "available"
        elif assortment_ok:
            status = "missing_inventory_run"
        else:
            status = combo.get("expected_status", "planned")
        rows.append(
            {
                "evaluation_id": evaluation_id,
                "comparison_type": "combination",
                "comparison_id": combo["combination_id"],
                "run_status": status,
                "metrics_status": inventory_row.get("metrics_status", "missing"),
                "method_name": combo["combination_id"],
                "method_family": "combination",
                "assortment_method": assortment_method,
                "inventory_method": inventory_method,
                "expected_assortment_version": assortment_row.get("expected_assortment_version", ""),
                "observed_assortment_version": assortment_row.get("observed_assortment_version", ""),
                "expected_inventory_version": inventory_row.get("expected_inventory_version", ""),
                "observed_inventory_version": inventory_row.get("observed_inventory_version", ""),
                "source_experiment_id": inventory_row.get("source_experiment_id", ""),
                "local_order_fulfillment_rate": assortment_row.get("local_order_fulfillment_rate", ""),
                "sku_frequency_recall_at_k": assortment_row.get("sku_frequency_recall_at_k", ""),
                "ndcg_at_k": assortment_row.get("ndcg_at_k", ""),
                "selected_sku_count": assortment_row.get("selected_sku_count", ""),
                "fdc_fulfillment_rate": inventory_row.get("fdc_fulfillment_rate", ""),
                "loss_ratio": inventory_row.get("loss_ratio", ""),
                "lost_sales_qty": inventory_row.get("lost_sales_qty", ""),
                "transfer_cost": inventory_row.get("transfer_cost", ""),
                "total_cost": inventory_row.get("total_cost", ""),
                "notes": "combination waits for a matching inventory run" if not inventory_ok else "",
            }
        )
    return rows
