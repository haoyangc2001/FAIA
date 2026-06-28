"""Collect manifests and normalize metrics for a FAIA evaluation."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from evaluation.src.common import (
    file_entry,
    infer_repo_root,
    nested_get,
    numeric_items,
    output_path,
    read_json,
    read_yaml,
    relative_path,
    resolve_path,
    row_count,
    to_text,
    validation_status,
    write_csv,
    write_yaml,
)
from evaluation.src.compare import COMPARISON_FIELDS, build_comparison_table
from evaluation.src.metrics import METRIC_FIELDS, metric_row


REGISTRY_FIELDS = [
    "evaluation_id",
    "stage",
    "experiment_id",
    "run_status",
    "method_name",
    "method_family",
    "data_version",
    "split_version",
    "feature_version",
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
    "run_path",
    "manifest_path",
    "metrics_path",
    "validation_status",
    "created_at",
    "notes",
]


ASSORTMENT_METHOD_FAMILIES = {
    "topk": "baseline",
    "reverse_exclude": "heuristic",
    "hybrid": "heuristic",
    "ml_topk": "ml_model",
}


def protocol_context(config: dict[str, Any]) -> dict[str, Any]:
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


def registry_row(
    config: dict[str, Any],
    stage: str,
    experiment_id: str,
    *,
    run_status: str,
    method_name: str = "",
    method_family: str = "",
    run_path: str = "",
    manifest_path: str = "",
    metrics_path: str = "",
    validation_status_value: str = "unknown",
    created_at: Any = "",
    notes: str = "",
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = {
        **protocol_context(config),
        "stage": stage,
        "experiment_id": experiment_id,
        "run_status": run_status,
        "method_name": method_name,
        "method_family": method_family,
        "feature_version": "",
        "run_path": run_path,
        "manifest_path": manifest_path,
        "metrics_path": metrics_path,
        "validation_status": validation_status_value,
        "created_at": to_text(created_at),
        "notes": notes,
    }
    if overrides:
        row.update({key: to_text(value) for key, value in overrides.items()})
    return row


def collect_results(config_path: Path) -> dict[str, Any]:
    config_path = config_path.resolve()
    repo_root = infer_repo_root(config_path)
    config = read_yaml(config_path)
    run_dir = resolve_path(config["expected_outputs"]["evaluation_manifest"], repo_root).parent
    run_dir.mkdir(parents=True, exist_ok=True)

    registry: list[dict[str, Any]] = []
    metrics: list[dict[str, Any]] = []

    for stage, sources in config.get("manifest_sources", {}).items():
        for source in sources:
            source_path = resolve_path(source, repo_root)
            if not source_path.exists():
                registry.append(missing_registry_row(config, stage, source, repo_root))
                continue
            manifest = read_yaml(source_path)
            if stage == "data":
                row, stage_metrics = collect_data_manifest(config, manifest, source_path, repo_root)
            elif stage == "assortment":
                row, stage_metrics = collect_assortment_manifest(config, manifest, source_path, repo_root)
            elif stage == "simulation":
                row, stage_metrics = collect_simulation_manifest(config, manifest, source_path, repo_root)
            elif stage == "inventory":
                row, stage_metrics = collect_inventory_manifest(config, manifest, source_path, repo_root)
            else:
                row = registry_row(
                    config,
                    stage,
                    source_path.parent.name,
                    run_status="skipped",
                    manifest_path=relative_path(source_path, repo_root),
                    notes=f"unsupported stage {stage}",
                )
                stage_metrics = []
            registry.append(row)
            metrics.extend(stage_metrics)

    comparison_rows = build_comparison_table(config, registry, metrics)

    experiment_registry_path = resolve_path(config["expected_outputs"]["experiment_registry"], repo_root)
    metrics_summary_path = resolve_path(config["expected_outputs"]["metrics_summary"], repo_root)
    comparison_table_path = resolve_path(config["expected_outputs"]["comparison_table"], repo_root)
    evaluation_manifest_path = resolve_path(config["expected_outputs"]["evaluation_manifest"], repo_root)

    write_csv(experiment_registry_path, registry, REGISTRY_FIELDS)
    write_csv(metrics_summary_path, metrics, METRIC_FIELDS)
    write_csv(comparison_table_path, comparison_rows, COMPARISON_FIELDS)

    manifest = build_evaluation_manifest(
        config,
        config_path,
        repo_root,
        registry,
        metrics,
        comparison_rows,
        {
            "experiment_registry": experiment_registry_path,
            "metrics_summary": metrics_summary_path,
            "comparison_table": comparison_table_path,
            "evaluation_manifest": evaluation_manifest_path,
        },
    )
    write_yaml(evaluation_manifest_path, manifest)
    manifest["outputs"]["evaluation_manifest"] = file_entry(evaluation_manifest_path, repo_root)
    write_yaml(evaluation_manifest_path, manifest)
    return manifest


def missing_registry_row(
    config: dict[str, Any],
    stage: str,
    source: str,
    repo_root: Path,
) -> dict[str, Any]:
    versions = config.get("versions", {})
    experiment_id = Path(source).parent.name or Path(source).stem
    method_name = ""
    method_family = ""
    overrides: dict[str, Any] = {}
    if stage == "inventory":
        method_name = "base_stock"
        method_family = "heuristic"
        experiment_id = to_text(versions.get("inventory_version", experiment_id))
        overrides["inventory_version"] = versions.get("inventory_version", "")
    return registry_row(
        config,
        stage,
        experiment_id,
        run_status=config.get("comparison_protocol", {}).get("missing_run_status", "missing"),
        method_name=method_name,
        method_family=method_family,
        run_path=relative_path(resolve_path(source, repo_root).parent, repo_root),
        manifest_path=source,
        validation_status_value="missing",
        notes=f"declared manifest does not exist: {source}",
        overrides=overrides,
    )


def collect_data_manifest(
    config: dict[str, Any],
    manifest: dict[str, Any],
    manifest_path: Path,
    repo_root: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    data_version = to_text(manifest.get("data_version", config["data_version"]))
    validation = manifest.get("validation", {})
    metrics_path = to_text(validation.get("summary", ""))
    row = registry_row(
        config,
        "data",
        data_version,
        run_status="available",
        method_name="data_version",
        method_family="data_artifact",
        run_path=relative_path(manifest_path.parent, repo_root),
        manifest_path=relative_path(manifest_path, repo_root),
        metrics_path=metrics_path,
        validation_status_value=to_text(validation.get("status", "unknown")),
        created_at=manifest.get("registered_at"),
        overrides={"data_version": data_version},
    )

    metrics: list[dict[str, Any]] = []
    synthetic_counts = nested_get(manifest, "artifacts.synthetic.counts", {}) or {}
    processed_counts = nested_get(manifest, "artifacts.processed.counts", {}) or {}
    split_counts = nested_get(manifest, "artifacts.splits.counts", {}) or {}
    summary_metrics = {
        "num_skus": synthetic_counts.get("sku_master"),
        "num_orders": synthetic_counts.get("orders"),
        "num_order_items": synthetic_counts.get("order_items"),
        "num_warehouses": synthetic_counts.get("warehouse_master"),
        "stockout_event_rows": synthetic_counts.get("stockout_events"),
        "candidate_pool_rows": processed_counts.get("candidate_pool_base"),
        "fdc_sku_daily_demand_rows": processed_counts.get("fdc_sku_daily_demand"),
        "inventory_daily_state_rows": processed_counts.get("inventory_daily_state"),
        "train_date_count": split_counts.get("train_dates"),
        "validation_date_count": split_counts.get("val_dates"),
        "test_date_count": split_counts.get("test_dates"),
        "validation_total_checks": validation.get("total_checks"),
        "validation_error_count": validation.get("failed_checks"),
        "validation_warning_count": validation.get("warnings"),
    }
    for name, value in summary_metrics.items():
        if value is None:
            continue
        metrics.append(
            metric_row(
                config,
                "data",
                data_version,
                name,
                value,
                method_name="data_version",
                method_family="data_artifact",
                source_path=relative_path(manifest_path, repo_root),
                overrides={"data_version": data_version},
            )
        )
    return row, metrics


def collect_assortment_manifest(
    config: dict[str, Any],
    manifest: dict[str, Any],
    manifest_path: Path,
    repo_root: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    experiment_id = to_text(manifest.get("experiment_id", manifest_path.parent.name))
    method_name = to_text(manifest.get("method", ""))
    method_family = ASSORTMENT_METHOD_FAMILIES.get(method_name, "unknown") if method_name else "unknown"
    outputs = manifest.get("outputs", {})
    metrics_rel_path = output_path(outputs.get("assortment_metrics", ""))
    metrics_path = resolve_path(metrics_rel_path, repo_root) if metrics_rel_path else None
    metrics_exists = bool(metrics_path and metrics_path.exists())
    row = registry_row(
        config,
        "assortment",
        experiment_id,
        run_status="available",
        method_name=method_name,
        method_family=method_family,
        run_path=relative_path(resolve_path(manifest.get("run_dir", manifest_path.parent), repo_root), repo_root),
        manifest_path=relative_path(manifest_path, repo_root),
        metrics_path=metrics_rel_path,
        validation_status_value=validation_status(manifest),
        created_at=manifest.get("created_at"),
        notes="" if metrics_exists else "assortment_metrics.json not found; collected manifest and run summary metrics only",
        overrides={
            "data_version": manifest.get("data_version", config["data_version"]),
            "candidate_pool_version": manifest.get("candidate_pool_version", ""),
            "k_rule_version": manifest.get("k_rule_version", ""),
            "assortment_version": manifest.get("assortment_version", ""),
            "model_version": manifest.get("model_version", ""),
        },
    )
    metrics = collect_assortment_metrics_json(config, experiment_id, metrics_path, repo_root) if metrics_exists else []
    metrics.extend(collect_assortment_manifest_metrics(config, manifest, manifest_path, repo_root))
    metrics.extend(collect_assortment_run_manifest_metrics(config, manifest, manifest_path, repo_root))
    return row, metrics


def collect_assortment_metrics_json(
    config: dict[str, Any],
    experiment_id: str,
    metrics_path: Path | None,
    repo_root: Path,
) -> list[dict[str, Any]]:
    if metrics_path is None:
        return []
    summary = read_json(metrics_path)
    rows: list[dict[str, Any]] = []
    for source_row in summary.get("metric_rows", []):
        method_name = method_from_version(to_text(source_row.get("method_version")))
        method_family = ASSORTMENT_METHOD_FAMILIES.get(method_name, "unknown")
        overrides = {
            "data_version": source_row.get("data_version", ""),
            "candidate_pool_version": source_row.get("candidate_pool_version", ""),
            "k_rule_version": source_row.get("k_rule_version", ""),
            "assortment_version": source_row.get("assortment_version", ""),
            "evaluation_split": source_row.get("evaluation_split", config["evaluation_split"]),
            "evaluation_start_date": source_row.get("evaluation_start_date", config["evaluation_window"]["start_date"]),
            "evaluation_end_date": source_row.get("evaluation_end_date", config["evaluation_window"]["end_date"]),
        }
        for name, value in numeric_items(source_row):
            if name in {"rank"}:
                continue
            rows.append(
                metric_row(
                    config,
                    "assortment",
                    experiment_id,
                    name,
                    value,
                    method_name=method_name,
                    method_family=method_family,
                    metric_level=to_text(source_row.get("metric_level", "overall")),
                    metric_key=to_text(source_row.get("metric_key", "ALL")),
                    source_path=relative_path(metrics_path, repo_root),
                    overrides=overrides,
                )
            )
    return rows


def collect_assortment_manifest_metrics(
    config: dict[str, Any],
    manifest: dict[str, Any],
    manifest_path: Path,
    repo_root: Path,
) -> list[dict[str, Any]]:
    experiment_id = to_text(manifest.get("experiment_id", manifest_path.parent.name))
    method_name = to_text(manifest.get("method", ""))
    method_family = ASSORTMENT_METHOD_FAMILIES.get(method_name, "unknown") if method_name else "unknown"
    rows: list[dict[str, Any]] = []
    for name, value in numeric_items(manifest.get("row_counts", {})):
        rows.append(
            metric_row(
                config,
                "assortment",
                experiment_id,
                f"{name}_rows",
                value,
                method_name=method_name,
                method_family=method_family,
                source_path=relative_path(manifest_path, repo_root),
                notes="from assortment_manifest row_counts",
                overrides={
                    "data_version": manifest.get("data_version", ""),
                    "candidate_pool_version": manifest.get("candidate_pool_version", ""),
                    "k_rule_version": manifest.get("k_rule_version", ""),
                    "assortment_version": manifest.get("assortment_version", ""),
                },
            )
        )
    return rows


def collect_assortment_run_manifest_metrics(
    config: dict[str, Any],
    manifest: dict[str, Any],
    manifest_path: Path,
    repo_root: Path,
) -> list[dict[str, Any]]:
    run_manifest_path = manifest_path.parent / "run_manifest.yaml"
    if not run_manifest_path.exists():
        return []
    run_manifest = read_yaml(run_manifest_path)
    experiment_id = to_text(run_manifest.get("experiment_id", manifest.get("experiment_id", manifest_path.parent.name)))
    method_versions = run_manifest.get("method_versions", {})
    assortment_versions = run_manifest.get("assortment_versions", {})
    rows: list[dict[str, Any]] = []
    for method_name in ["topk", "reverse_exclude", "hybrid", "ml_topk"]:
        summary = run_manifest.get(f"{method_name}_summary", {}) or {}
        method_family = ASSORTMENT_METHOD_FAMILIES.get(method_name, "unknown")
        overrides = {
            "data_version": run_manifest.get("data_version", ""),
            "candidate_pool_version": run_manifest.get("candidate_pool_version", ""),
            "k_rule_version": run_manifest.get("k_rule_version", ""),
            "assortment_version": assortment_versions.get(method_name, ""),
            "model_version": summary.get("model_version", ""),
        }
        for name, value in numeric_items(summary):
            rows.append(
                metric_row(
                    config,
                    "assortment",
                    experiment_id,
                    name,
                    value,
                    method_name=method_name,
                    method_family=method_family,
                    source_path=relative_path(run_manifest_path, repo_root),
                    notes="from assortment run_manifest method summary",
                    overrides={**overrides, "policy_version": method_versions.get(method_name, "")},
                )
            )
    return rows


def collect_simulation_manifest(
    config: dict[str, Any],
    manifest: dict[str, Any],
    manifest_path: Path,
    repo_root: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    experiment_id = to_text(manifest.get("experiment_id", manifest_path.parent.name))
    outputs = manifest.get("outputs", {})
    metrics_rel_path = output_path(outputs.get("metrics_summary", ""))
    metrics_path = resolve_path(metrics_rel_path, repo_root) if metrics_rel_path else None
    row = registry_row(
        config,
        "simulation",
        experiment_id,
        run_status="available",
        method_name=policy_method_name(to_text(manifest.get("policy_version", ""))),
        method_family="baseline",
        run_path=relative_path(resolve_path(manifest.get("run_dir", manifest_path.parent), repo_root), repo_root),
        manifest_path=relative_path(manifest_path, repo_root),
        metrics_path=metrics_rel_path,
        validation_status_value=validation_status(manifest),
        created_at=manifest.get("created_at"),
        overrides={
            "data_version": manifest.get("data_version", ""),
            "assortment_version": manifest.get("assortment_version", ""),
            "simulation_rule_version": manifest.get("simulation_rule_version", ""),
            "policy_version": manifest.get("policy_version", ""),
            "evaluation_start_date": manifest.get("simulation_start_date", ""),
            "evaluation_end_date": manifest.get("simulation_end_date", ""),
        },
    )
    summary = read_json(metrics_path) if metrics_path and metrics_path.exists() else manifest.get("metrics_summary", {})
    metrics = collect_operational_metrics(config, "simulation", experiment_id, summary, manifest_path, repo_root, row)
    metrics.extend(collect_row_count_metrics(config, "simulation", experiment_id, manifest, manifest_path, repo_root, row))
    return row, metrics


def collect_inventory_manifest(
    config: dict[str, Any],
    manifest: dict[str, Any],
    manifest_path: Path,
    repo_root: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    experiment_id = to_text(manifest.get("experiment_id", manifest_path.parent.name))
    outputs = manifest.get("outputs", {})
    metrics_rel_path = output_path(outputs.get("simulation_metrics", "")) or output_path(outputs.get("metrics_summary", ""))
    row = registry_row(
        config,
        "inventory",
        experiment_id,
        run_status="available",
        method_name=to_text(manifest.get("policy_name", "")),
        method_family="heuristic",
        run_path=relative_path(resolve_path(manifest.get("run_dir", manifest_path.parent), repo_root), repo_root),
        manifest_path=relative_path(manifest_path, repo_root),
        metrics_path=metrics_rel_path,
        validation_status_value=validation_status(manifest),
        created_at=manifest.get("created_at"),
        overrides={
            "data_version": manifest.get("data_version", ""),
            "assortment_version": manifest.get("assortment_version", ""),
            "inventory_version": manifest.get("inventory_version", ""),
            "simulation_rule_version": manifest.get("simulation_rule_version", ""),
            "policy_version": manifest.get("policy_version", ""),
            "model_version": manifest.get("model_version", ""),
            "evaluation_start_date": manifest.get("effective_start_date", ""),
            "evaluation_end_date": manifest.get("effective_end_date", ""),
        },
    )
    summary = nested_get(manifest, "simulation.metrics_summary", {}) or {}
    metrics = collect_operational_metrics(config, "inventory", experiment_id, summary, manifest_path, repo_root, row)
    metrics.extend(collect_row_count_metrics(config, "inventory", experiment_id, manifest, manifest_path, repo_root, row))
    return row, metrics


def collect_operational_metrics(
    config: dict[str, Any],
    stage: str,
    experiment_id: str,
    summary: dict[str, Any],
    manifest_path: Path,
    repo_root: Path,
    registry: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    overrides = {
        "data_version": registry.get("data_version", ""),
        "assortment_version": registry.get("assortment_version", ""),
        "inventory_version": registry.get("inventory_version", ""),
        "simulation_rule_version": registry.get("simulation_rule_version", ""),
        "policy_version": registry.get("policy_version", ""),
        "model_version": registry.get("model_version", ""),
        "evaluation_start_date": registry.get("evaluation_start_date", ""),
        "evaluation_end_date": registry.get("evaluation_end_date", ""),
    }
    for name, value in numeric_items(summary):
        rows.append(
            metric_row(
                config,
                stage,
                experiment_id,
                name,
                value,
                method_name=to_text(registry.get("method_name", "")),
                method_family=to_text(registry.get("method_family", "")),
                source_path=relative_path(manifest_path, repo_root),
                overrides=overrides,
            )
        )
    return rows


def collect_row_count_metrics(
    config: dict[str, Any],
    stage: str,
    experiment_id: str,
    manifest: dict[str, Any],
    manifest_path: Path,
    repo_root: Path,
    registry: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, value in numeric_items(manifest.get("row_counts", {})):
        rows.append(
            metric_row(
                config,
                stage,
                experiment_id,
                f"{name}_rows",
                value,
                method_name=to_text(registry.get("method_name", "")),
                method_family=to_text(registry.get("method_family", "")),
                source_path=relative_path(manifest_path, repo_root),
                notes="from manifest row_counts",
                overrides={
                    "data_version": registry.get("data_version", ""),
                    "assortment_version": registry.get("assortment_version", ""),
                    "inventory_version": registry.get("inventory_version", ""),
                    "simulation_rule_version": registry.get("simulation_rule_version", ""),
                    "policy_version": registry.get("policy_version", ""),
                    "model_version": registry.get("model_version", ""),
                    "evaluation_start_date": registry.get("evaluation_start_date", ""),
                    "evaluation_end_date": registry.get("evaluation_end_date", ""),
                },
            )
        )
    return rows


def build_evaluation_manifest(
    config: dict[str, Any],
    config_path: Path,
    repo_root: Path,
    registry: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
    comparison_rows: list[dict[str, Any]],
    output_paths: dict[str, Path],
) -> dict[str, Any]:
    versions = config.get("versions", {})
    window = config["evaluation_window"]
    available_count = sum(1 for row in registry if row["run_status"] == "available")
    missing_count = sum(1 for row in registry if row["run_status"] in {"missing", "not_run"})
    outputs = {
        "experiment_registry": file_entry(output_paths["experiment_registry"], repo_root, row_count(output_paths["experiment_registry"])),
        "metrics_summary": file_entry(output_paths["metrics_summary"], repo_root, row_count(output_paths["metrics_summary"])),
        "comparison_table": file_entry(output_paths["comparison_table"], repo_root, row_count(output_paths["comparison_table"])),
    }
    return {
        "evaluation_id": config["evaluation_id"],
        "evaluation_version": config["evaluation_version"],
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "status": "collected",
        "config": relative_path(config_path, repo_root),
        "run_dir": relative_path(output_paths["evaluation_manifest"].parent, repo_root),
        "protocol": {
            "data_version": config["data_version"],
            "split_version": config["split_version"],
            "evaluation_split": config["evaluation_split"],
            "evaluation_window": {
                "start_date": to_text(window["start_date"]),
                "end_date": to_text(window["end_date"]),
            },
            "candidate_pool_version": versions.get("candidate_pool_version", ""),
            "k_rule_version": versions.get("k_rule_version", ""),
            "assortment_version": versions.get("assortment_version", ""),
            "inventory_version": versions.get("inventory_version", ""),
            "simulation_rule_version": versions.get("simulation_rule_version", ""),
            "cost_config_version": versions.get("cost_config_version", ""),
            "cost_config_path": versions.get("cost_config_path", ""),
        },
        "comparison_protocol": config.get("comparison_protocol", {}),
        "manifest_sources": config.get("manifest_sources", {}),
        "baseline_matrix": config.get("baseline_matrix", {}),
        "row_counts": {
            "experiment_registry": len(registry),
            "metrics_summary": len(metrics),
            "comparison_table": len(comparison_rows),
        },
        "collection_summary": {
            "available_runs": available_count,
            "missing_runs": missing_count,
            "metric_rows_by_stage": metric_rows_by_stage(metrics),
        },
        "expected_outputs": config.get("expected_outputs", {}),
        "outputs": outputs,
        "validation": {
            "status": "not_run",
            "reason": "Evaluation validation is implemented in Phase 5.8.",
        },
        "replay_command": f"PYTHONPATH=. python3 evaluation/scripts/collect_results.py --config {relative_path(config_path, repo_root)}",
    }


def metric_rows_by_stage(metrics: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in metrics:
        stage = to_text(row.get("stage"))
        counts[stage] = counts.get(stage, 0) + 1
    return counts


def method_from_version(method_version: str) -> str:
    if method_version.endswith("_v001"):
        return method_version[: -len("_v001")]
    return method_version


def policy_method_name(policy_version: str) -> str:
    for prefix in [
        "no_transfer",
        "historical_mean",
        "base_stock",
        "greedy_allocation",
        "parameter_search",
        "e2e_inventory_model",
    ]:
        if policy_version.startswith(prefix):
            return prefix
    if policy_version.endswith("_v001"):
        return policy_version[: -len("_v001")]
    return policy_version
