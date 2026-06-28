"""Validation for FAIA evaluation runs."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from evaluation.src.common import file_entry, infer_repo_root, output_path, read_csv_rows, read_yaml, relative_path, resolve_path, row_count, to_text, write_json, write_yaml


def validate_evaluation_run(manifest_path: Path, update_manifest: bool = True) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    repo_root = infer_repo_root(manifest_path)
    manifest = read_yaml(manifest_path)
    checks: list[dict[str, Any]] = []

    paths = build_paths(manifest, repo_root)
    validate_required_files(paths, checks)
    registry = read_csv_rows(paths["experiment_registry"]) if paths["experiment_registry"].exists() else []
    metrics = read_csv_rows(paths["metrics_summary"]) if paths["metrics_summary"].exists() else []
    comparison = read_csv_rows(paths["comparison_table"]) if paths["comparison_table"].exists() else []

    validate_row_counts(manifest, paths, checks)
    validate_registry_protocol(manifest, registry, checks)
    validate_metric_protocol(manifest, metrics, checks)
    validate_metric_completeness(registry, metrics, comparison, checks)
    validate_metric_ranges(metrics, comparison, checks)
    validate_conservation(metrics, checks)
    validate_missing_artifacts(registry, comparison, checks)

    passed = all(check["passed"] for check in checks)
    summary = {
        "evaluation_id": manifest["evaluation_id"],
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "manifest_path": relative_path(manifest_path, repo_root),
        "passed": passed,
        "checks": checks,
        "metrics": {
            "registry_rows": len(registry),
            "metrics_rows": len(metrics),
            "comparison_rows": len(comparison),
            "failed_checks": sum(1 for check in checks if not check["passed"]),
        },
    }

    summary_path = resolve_path(
        output_path(manifest.get("expected_outputs", {}).get("evaluation_validation_summary", ""))
        or f"evaluation/runs/{manifest['evaluation_id']}/evaluation_validation_summary.json",
        repo_root,
    )
    report_path = resolve_path(
        output_path(manifest.get("expected_outputs", {}).get("evaluation_validation_report", ""))
        or f"evaluation/reports/{manifest['evaluation_id']}_validation_report.md",
        repo_root,
    )
    write_json(summary_path, summary)
    write_validation_report(report_path, summary)

    if update_manifest:
        manifest["status"] = "validated" if passed else "failed"
        manifest["validation"] = {
            "passed": passed,
            "checked_at": summary["checked_at"],
            "validation_summary": relative_path(summary_path, repo_root),
            "validation_report": relative_path(report_path, repo_root),
        }
        manifest.setdefault("outputs", {})
        manifest["outputs"]["evaluation_validation_summary"] = file_entry(summary_path, repo_root)
        manifest["outputs"]["evaluation_validation_report"] = file_entry(report_path, repo_root)
        write_yaml(manifest_path, manifest)
        manifest["outputs"]["evaluation_manifest"] = file_entry(manifest_path, repo_root)
        write_yaml(manifest_path, manifest)
        summary["manifest_updated"] = True
    return summary


def build_paths(manifest: dict[str, Any], repo_root: Path) -> dict[str, Path]:
    outputs = manifest.get("outputs", {})
    expected = manifest.get("expected_outputs", {})
    names = [
        "experiment_registry",
        "metrics_summary",
        "comparison_table",
        "evaluation_report",
    ]
    paths: dict[str, Path] = {}
    for name in names:
        raw = output_path(outputs.get(name, "")) or output_path(expected.get(name, ""))
        if raw:
            paths[name] = resolve_path(raw, repo_root)
    return paths


def add_check(checks: list[dict[str, Any]], name: str, passed: bool, detail: str, metrics: dict[str, Any] | None = None) -> None:
    checks.append({"name": name, "passed": passed, "detail": detail, "metrics": metrics or {}})


def validate_required_files(paths: dict[str, Path], checks: list[dict[str, Any]]) -> None:
    required = ["experiment_registry", "metrics_summary", "comparison_table", "evaluation_report"]
    missing = [name for name in required if name not in paths or not paths[name].exists()]
    add_check(
        checks,
        "required_files_exist",
        not missing,
        "all evaluation registry, metrics, comparison and report files exist" if not missing else f"missing files: {missing}",
        {"missing_files": missing, "checked_files": len(required)},
    )


def validate_row_counts(manifest: dict[str, Any], paths: dict[str, Path], checks: list[dict[str, Any]]) -> None:
    expected = manifest.get("row_counts", {})
    actual = {
        name: row_count(paths[name])
        for name in ["experiment_registry", "metrics_summary", "comparison_table"]
        if name in paths and paths[name].exists()
    }
    mismatches = {name: {"expected": expected.get(name), "actual": value} for name, value in actual.items() if expected.get(name) != value}
    add_check(
        checks,
        "row_counts_match_manifest",
        not mismatches,
        "CSV row counts match evaluation_manifest" if not mismatches else f"row count mismatches: {mismatches}",
        {"expected": expected, "actual": actual},
    )


def validate_registry_protocol(manifest: dict[str, Any], registry: list[dict[str, str]], checks: list[dict[str, Any]]) -> None:
    protocol = manifest["protocol"]
    errors = []
    for row in registry:
        label = f"{row.get('stage')}:{row.get('experiment_id')}"
        for field, protocol_key in [
            ("data_version", "data_version"),
            ("split_version", "split_version"),
            ("evaluation_split", "evaluation_split"),
        ]:
            if row.get(field) != to_text(protocol.get(protocol_key)):
                errors.append(f"{label} {field} mismatch")
        window = protocol["evaluation_window"]
        if not registry_window_matches_protocol(row, window):
            errors.append(f"{label} evaluation_window mismatch")
        for field in ["simulation_rule_version", "cost_config_version"]:
            value = row.get(field, "")
            if value and value != to_text(protocol.get(field)):
                errors.append(f"{label} {field} mismatch")
    add_check(
        checks,
        "registry_protocol_consistent",
        not errors,
        "registry rows share the evaluation protocol" if not errors else "; ".join(errors[:10]),
        {"error_count": len(errors)},
    )


def registry_window_matches_protocol(row: dict[str, str], window: dict[str, Any]) -> bool:
    start = row.get("evaluation_start_date", "")
    end = row.get("evaluation_end_date", "")
    protocol_start = to_text(window["start_date"])
    protocol_end = to_text(window["end_date"])
    if row.get("stage") == "inventory" and row.get("run_status") == "available":
        return start == protocol_start and protocol_start <= end <= protocol_end
    return start == protocol_start and end == protocol_end


def validate_metric_protocol(manifest: dict[str, Any], metrics_rows: list[dict[str, str]], checks: list[dict[str, Any]]) -> None:
    protocol = manifest["protocol"]
    errors = []
    for row in metrics_rows:
        label = f"{row.get('stage')}:{row.get('experiment_id')}:{row.get('metric_name')}"
        for field, protocol_key in [
            ("data_version", "data_version"),
            ("split_version", "split_version"),
            ("evaluation_split", "evaluation_split"),
        ]:
            if row.get(field) != to_text(protocol.get(protocol_key)):
                errors.append(f"{label} {field} mismatch")
        for field in ["simulation_rule_version", "cost_config_version"]:
            value = row.get(field, "")
            if value and value != to_text(protocol.get(field)):
                errors.append(f"{label} {field} mismatch")
    add_check(
        checks,
        "metric_protocol_consistent",
        not errors,
        "metric rows share the evaluation protocol" if not errors else "; ".join(errors[:10]),
        {"error_count": len(errors)},
    )


def validate_metric_completeness(
    registry: list[dict[str, str]],
    metrics_rows: list[dict[str, str]],
    comparison: list[dict[str, str]],
    checks: list[dict[str, Any]],
) -> None:
    metric_keys = {(row.get("stage"), row.get("method_name"), row.get("metric_name")) for row in metrics_rows}
    missing = []
    for name in ["num_orders", "num_order_items", "num_skus", "validation_error_count"]:
        if ("data", "data_version", name) not in metric_keys:
            missing.append(f"data.{name}")
    for name in ["total_demand_qty", "fdc_fulfillment_rate", "loss_ratio", "total_cost"]:
        if ("simulation", "no_transfer", name) not in metric_keys:
            missing.append(f"simulation.no_transfer.{name}")
    if not any(row.get("comparison_id") == "no_transfer" and row.get("metrics_status") == "available" for row in comparison):
        missing.append("comparison.no_transfer.available")
    available_inventory = [
        row
        for row in registry
        if row.get("stage") == "inventory" and row.get("run_status") == "available"
    ]
    missing_inventory = [
        row
        for row in registry
        if row.get("stage") == "inventory" and row.get("run_status") == "missing"
    ]
    if available_inventory:
        for row in available_inventory:
            method_name = row.get("method_name", "")
            if ("inventory", method_name, "transfer_recommendation_rows") not in metric_keys:
                missing.append(f"inventory.{method_name}.transfer_recommendation_rows")
    elif missing_inventory:
        pass
    else:
        missing.append("registry.inventory_available_or_missing_marker")
    add_check(
        checks,
        "required_metrics_present",
        not missing,
        "required evaluation metrics are present" if not missing else f"missing metrics: {missing}",
        {"missing": missing},
    )


def validate_metric_ranges(metrics_rows: list[dict[str, str]], comparison: list[dict[str, str]], checks: list[dict[str, Any]]) -> None:
    errors = []
    for row in metrics_rows:
        name = row.get("metric_name", "")
        unit = row.get("metric_unit", "")
        value = parse_float(row.get("metric_value", ""))
        if value is None:
            errors.append(f"{name} is not numeric")
            continue
        if unit == "ratio" and not (0.0 <= value <= 1.0):
            errors.append(f"{name} ratio out of range")
        if unit in {"count", "qty", "cost"} and value < 0:
            errors.append(f"{name} negative {unit}")
    for row in comparison:
        for field in ["local_order_fulfillment_rate", "sku_frequency_recall_at_k", "ndcg_at_k", "fdc_fulfillment_rate", "loss_ratio"]:
            value = parse_float(row.get(field, ""))
            if value is not None and not (0.0 <= value <= 1.0):
                errors.append(f"comparison {row.get('comparison_id')} {field} out of range")
    add_check(
        checks,
        "metric_ranges_valid",
        not errors,
        "metric values satisfy ratio and non-negative bounds" if not errors else "; ".join(errors[:10]),
        {"error_count": len(errors)},
    )


def validate_conservation(metrics_rows: list[dict[str, str]], checks: list[dict[str, Any]]) -> None:
    grouped: dict[tuple[str, str, str], dict[str, float]] = {}
    for row in metrics_rows:
        if row.get("stage") not in {"simulation", "inventory"}:
            continue
        key = (row.get("stage", ""), row.get("experiment_id", ""), row.get("method_name", ""))
        grouped.setdefault(key, {})
        value = parse_float(row.get("metric_value", ""))
        if value is not None:
            grouped[key][row.get("metric_name", "")] = value
    demand_errors = []
    cost_errors = []
    for key, values in grouped.items():
        if {"total_demand_qty", "fdc_fulfilled_qty", "rdc_fallback_qty", "lost_sales_qty"} <= set(values):
            expected = values["fdc_fulfilled_qty"] + values["rdc_fallback_qty"] + values["lost_sales_qty"]
            if abs(values["total_demand_qty"] - expected) > 1e-6:
                demand_errors.append(f"{key} demand conservation mismatch")
        if {"transfer_cost", "rdc_fallback_cost", "lost_sales_cost", "holding_cost", "total_cost"} <= set(values):
            expected = values["transfer_cost"] + values["rdc_fallback_cost"] + values["lost_sales_cost"] + values["holding_cost"]
            if abs(values["total_cost"] - expected) > 1e-6:
                cost_errors.append(f"{key} cost conservation mismatch")
    add_check(
        checks,
        "demand_conservation",
        not demand_errors,
        "operational demand metrics conserve total demand" if not demand_errors else "; ".join(demand_errors),
        {"error_count": len(demand_errors)},
    )
    add_check(
        checks,
        "cost_conservation",
        not cost_errors,
        "operational cost metrics conserve total cost" if not cost_errors else "; ".join(cost_errors),
        {"error_count": len(cost_errors)},
    )


def validate_missing_artifacts(
    registry: list[dict[str, str]],
    comparison: list[dict[str, str]],
    checks: list[dict[str, Any]],
) -> None:
    errors = []
    for row in registry:
        if row.get("run_status") in {"missing", "not_run", "invalid"} and not row.get("notes"):
            errors.append(f"registry {row.get('stage')}:{row.get('experiment_id')} missing note")
    for row in comparison:
        if row.get("run_status") in {"missing", "not_run", "missing_inventory_run"} and not row.get("notes"):
            errors.append(f"comparison {row.get('comparison_id')} missing note")
    add_check(
        checks,
        "missing_artifacts_explicit",
        not errors,
        "missing artifacts are explicitly represented with notes" if not errors else "; ".join(errors[:10]),
        {"error_count": len(errors)},
    )


def parse_float(value: str) -> float | None:
    if value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def write_validation_report(report_path: Path, summary: dict[str, Any]) -> None:
    lines = [
        f"# Evaluation Validation Report: {summary['evaluation_id']}",
        "",
        f"- passed: {summary['passed']}",
        f"- checked_at: {summary['checked_at']}",
        f"- manifest_path: {summary['manifest_path']}",
        f"- failed_checks: {summary['metrics']['failed_checks']}",
        "",
        "## Checks",
        "",
    ]
    for check in summary["checks"]:
        lines.extend(
            [
                f"### {check['name']}",
                "",
                f"- passed: {check['passed']}",
                f"- detail: {check['detail']}",
                f"- metrics: {check['metrics']}",
                "",
            ]
        )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")
