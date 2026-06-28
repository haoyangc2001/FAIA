"""Run-level validation for FAIA inventory allocation outputs."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from inventory.src.common import (
    add_days,
    count_csv_rows,
    file_entry,
    float_value,
    int_value,
    iter_csv_rows,
    read_bool,
    read_yaml,
    write_json,
    write_yaml,
)
from inventory.src.manifest import write_inventory_report


def add_check(checks: list[dict[str, Any]], name: str, passed: bool, detail: str, metrics: dict[str, Any] | None = None) -> None:
    item: dict[str, Any] = {"name": name, "passed": bool(passed), "detail": detail}
    if metrics is not None:
        item["metrics"] = metrics
    checks.append(item)


def resolve_path(path_text: str, repo_root: Path) -> Path:
    path = Path(path_text)
    return path if path.is_absolute() else repo_root / path


def infer_repo_root(manifest_path: Path, manifest: dict[str, Any]) -> Path:
    config = Path(str(manifest.get("config", "")))
    if config.is_absolute():
        return config.parent
    for candidate in [Path.cwd(), *manifest_path.resolve().parents]:
        if (candidate / config).exists():
            return candidate
    return Path.cwd()


def output_path(manifest: dict[str, Any], name: str, repo_root: Path) -> Path:
    return resolve_path(str(manifest["outputs"][name]["path"]), repo_root)


def validate_inventory_run(
    manifest_path: Path,
    write_outputs: bool = True,
    update_manifest: bool = True,
) -> dict[str, Any]:
    manifest = read_yaml(manifest_path)
    repo_root = infer_repo_root(manifest_path, manifest)
    checks: list[dict[str, Any]] = []

    validate_required_files(manifest, repo_root, checks)
    validate_row_counts(manifest, repo_root, checks)
    validate_version_lineage(manifest, repo_root, checks)
    validate_inventory_state(manifest, repo_root, checks)
    validate_forecast(manifest, repo_root, checks)
    validate_tiss(manifest, repo_root, checks)
    validate_transfer_recommendation(manifest, repo_root, checks)
    validate_simulation_metrics(manifest, repo_root, checks)

    passed = all(check["passed"] for check in checks)
    summary = {
        "experiment_id": manifest["experiment_id"],
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "manifest_path": str(manifest_path),
        "passed": passed,
        "checks": checks,
        "metrics": {
            "checked_outputs": len(manifest.get("outputs", {})),
        },
    }
    if write_outputs:
        run_dir = resolve_path(str(manifest["run_dir"]), repo_root)
        report_dir = repo_root / "inventory" / "reports"
        summary_path = run_dir / "inventory_validation_summary.json"
        report_path = report_dir / f"{manifest['experiment_id']}_inventory_report.md"
        write_json(summary_path, summary)
        write_inventory_report(report_path, manifest, validation_summary=summary)
        if update_manifest:
            manifest["validation"] = {
                "passed": passed,
                "checked_at": summary["checked_at"],
                "validation_summary": str(summary_path.relative_to(repo_root)),
                "inventory_report": str(report_path.relative_to(repo_root)),
            }
            manifest["outputs"]["inventory_validation_summary"] = file_entry(summary_path)
            manifest["outputs"]["inventory_report"] = file_entry(report_path)
            write_yaml(manifest_path, manifest)
            summary["manifest_updated"] = True
    return summary


def validate_required_files(manifest: dict[str, Any], repo_root: Path, checks: list[dict[str, Any]]) -> None:
    missing = []
    for name, entry in manifest.get("outputs", {}).items():
        path = resolve_path(str(entry["path"]), repo_root)
        if not path.exists():
            missing.append(name)
    add_check(checks, "required_outputs_exist", not missing, "all declared outputs exist" if not missing else f"missing outputs: {missing}")


def validate_row_counts(manifest: dict[str, Any], repo_root: Path, checks: list[dict[str, Any]]) -> None:
    errors = []
    for name, expected in manifest.get("row_counts", {}).items():
        if name not in manifest.get("outputs", {}):
            continue
        path = output_path(manifest, name, repo_root)
        if path.suffix != ".csv":
            continue
        actual = count_csv_rows(path)
        if actual != expected:
            errors.append(f"{name}: expected={expected}, actual={actual}")
    add_check(checks, "row_counts_match", not errors, "all CSV row counts match manifest" if not errors else "; ".join(errors))


def validate_version_lineage(manifest: dict[str, Any], repo_root: Path, checks: list[dict[str, Any]]) -> None:
    expected = {
        "experiment_id": manifest["experiment_id"],
        "data_version": manifest["data_version"],
        "assortment_version": manifest["assortment_version"],
        "inventory_version": manifest["inventory_version"],
        "simulation_rule_version": manifest["simulation_rule_version"],
    }
    errors = []
    lineage = manifest.get("version_lineage", {})
    for field, value in expected.items():
        if lineage.get(field) != value:
            errors.append(f"version_lineage.{field}")
    for output in ["inventory_state", "demand_forecast", "tiss_result", "transfer_recommendation"]:
        path = output_path(manifest, output, repo_root)
        for row in iter_csv_rows(path):
            for field, value in expected.items():
                if str(row.get(field)) != str(value):
                    errors.append(f"{output}.{field}")
                    break
            break
    add_check(checks, "version_lineage_consistent", not errors, "version fields are consistent" if not errors else f"errors={sorted(set(errors))}")


def validate_inventory_state(manifest: dict[str, Any], repo_root: Path, checks: list[dict[str, Any]]) -> None:
    errors = 0
    for row in iter_csv_rows(output_path(manifest, "inventory_state", repo_root)):
        values = [
            int_value(row["on_hand_qty"]),
            int_value(row["reserved_qty"]),
            int_value(row["available_qty"]),
            int_value(row["in_transit_qty"]),
            int_value(row["inventory_position_qty"]),
            int_value(row["lead_time_days"]),
            int_value(row["rdc_reserved_qty"]),
            int_value(row["rdc_allocatable_qty"]),
        ]
        if min(values) < 0:
            errors += 1
        if int_value(row["inventory_position_qty"]) != int_value(row["available_qty"]) + int_value(row["in_transit_qty"]):
            errors += 1
        if row["node_type"] == "FDC" and not row["fdc_id"]:
            errors += 1
    add_check(checks, "inventory_state_valid", errors == 0, f"errors={errors}")


def validate_forecast(manifest: dict[str, Any], repo_root: Path, checks: list[dict[str, Any]]) -> None:
    errors = 0
    for row in iter_csv_rows(output_path(manifest, "demand_forecast", repo_root)):
        if float_value(row["forecast_qty"]) < 0 or float_value(row["base_forecast_qty"]) < 0:
            errors += 1
        if row["feature_window_end_date"] > row["decision_date"]:
            errors += 1
        if not read_bool(row["leakage_safe_flag"]):
            errors += 1
    add_check(checks, "demand_forecast_valid", errors == 0, f"errors={errors}")


def validate_tiss(manifest: dict[str, Any], repo_root: Path, checks: list[dict[str, Any]]) -> None:
    errors = 0
    for row in iter_csv_rows(output_path(manifest, "tiss_result", repo_root)):
        ss = int_value(row["safety_stock_qty"])
        ti = int_value(row["target_inventory_qty"])
        if ss < 0 or ti < ss:
            errors += 1
        if row["node_type"] == "FDC" and (not read_bool(row["assortment_mask"]) or not read_bool(row["eligible_mask"])) and (ss != 0 or ti != 0):
            errors += 1
    add_check(checks, "tiss_result_valid", errors == 0, f"errors={errors}")


def validate_transfer_recommendation(manifest: dict[str, Any], repo_root: Path, checks: list[dict[str, Any]]) -> None:
    errors = 0
    for row in iter_csv_rows(output_path(manifest, "transfer_recommendation", repo_root)):
        recommended = int_value(row["recommended_transfer_qty"])
        actual = int_value(row["actual_transfer_qty"]) if row.get("actual_transfer_qty") else recommended
        clipped = int_value(row["clipped_qty"]) if row.get("clipped_qty") else max(0, recommended - actual)
        if recommended < 0 or actual < 0 or clipped < 0:
            errors += 1
        if actual + clipped != recommended:
            errors += 1
        if actual > int_value(row["rdc_allocatable_qty"]):
            errors += 1
        if not read_bool(row["assortment_mask"]) and recommended != 0:
            errors += 1
        if not read_bool(row["eligible_mask"]) and recommended != 0:
            errors += 1
        if row["arrival_date"] != add_days(row["ship_date"], int_value(row["lead_time_days"])):
            errors += 1
    add_check(checks, "transfer_recommendation_valid", errors == 0, f"errors={errors}")


def validate_simulation_metrics(manifest: dict[str, Any], repo_root: Path, checks: list[dict[str, Any]]) -> None:
    if manifest.get("simulation", {}).get("status") != "completed":
        add_check(checks, "simulation_metrics_valid", True, "simulation skipped")
        return
    path = output_path(manifest, "simulation_metrics", repo_root)
    metrics = json.loads(path.read_text(encoding="utf-8"))
    total = int(metrics["total_demand_qty"])
    parts = int(metrics["fdc_fulfilled_qty"]) + int(metrics["rdc_fallback_qty"]) + int(metrics["lost_sales_qty"])
    cost = float(metrics["transfer_cost"]) + float(metrics["rdc_fallback_cost"]) + float(metrics["lost_sales_cost"]) + float(metrics["holding_cost"])
    errors = 0
    if total != parts:
        errors += 1
    if abs(float(metrics["total_cost"]) - cost) > 1e-6:
        errors += 1
    add_check(checks, "simulation_metrics_valid", errors == 0, f"errors={errors}")
