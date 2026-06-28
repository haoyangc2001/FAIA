"""Inventory run manifest and report helpers."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from inventory.src.common import file_entry, write_yaml


def build_inventory_manifest(
    config_path: Path,
    config: dict[str, Any],
    row_counts: dict[str, int],
    output_paths: dict[str, Path],
    simulation_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    outputs = {name: file_entry(path, rows=row_counts.get(name)) for name, path in output_paths.items()}
    manifest = {
        "experiment_id": config["experiment_id"],
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "data_version": config["data_version"],
        "assortment_version": config["assortment_version"],
        "inventory_version": config["inventory_version"],
        "simulation_rule_version": config["simulation_rule_version"],
        "policy_name": config["policy"]["policy_name"],
        "policy_version": config["policy"]["policy_version"],
        "model_version": config["policy"].get("model_version", "none"),
        "decision_date": config["decision_date"],
        "effective_start_date": config["effective_start_date"],
        "effective_end_date": config["effective_end_date"],
        "initial_inventory_date": config["initial_inventory_date"],
        "forecast_horizon_days": config["forecast"]["horizon_days"],
        "rollout_window_days": config["simulation"].get("rollout_window_days"),
        "config": str(config_path),
        "run_dir": config["output"]["run_dir"],
        "inputs": {
            **{name: str(path) for name, path in config.get("inputs", {}).items()},
            "simulation_rule": str(config["rules"]["simulation_rule"]),
        },
        "version_lineage": {
            "experiment_id": config["experiment_id"],
            "data_version": config["data_version"],
            "assortment_version": config["assortment_version"],
            "inventory_version": config["inventory_version"],
            "simulation_rule_version": config["simulation_rule_version"],
            "policy_name": config["policy"]["policy_name"],
            "policy_version": config["policy"]["policy_version"],
            "model_version": config["policy"].get("model_version", "none"),
            "config_path": str(config_path),
        },
        "row_counts": row_counts,
        "outputs": outputs,
        "simulation": {
            "enabled": bool(config.get("simulation", {}).get("enabled", False)),
            "status": "completed" if simulation_summary else "skipped",
        },
        "replay_command": f"PYTHONPATH=. python3 inventory/scripts/run_inventory_baseline.py --config {config_path}",
    }
    if simulation_summary:
        manifest["simulation"]["metrics_summary"] = simulation_summary["metrics_summary"]
    return manifest


def write_inventory_manifest(path: Path, manifest: dict[str, Any]) -> None:
    write_yaml(path, manifest)
    manifest["outputs"]["inventory_manifest"] = file_entry(path)
    write_yaml(path, manifest)


def write_inventory_report(report_path: Path, manifest: dict[str, Any], validation_summary: dict[str, Any] | None = None) -> None:
    metrics = manifest.get("simulation", {}).get("metrics_summary")
    lines = [
        f"# Inventory Report: {manifest['experiment_id']}",
        "",
        f"- data_version: {manifest['data_version']}",
        f"- assortment_version: {manifest['assortment_version']}",
        f"- inventory_version: {manifest['inventory_version']}",
        f"- policy_version: {manifest['policy_version']}",
        f"- simulation_rule_version: {manifest['simulation_rule_version']}",
        f"- decision_date: {manifest['decision_date']}",
        f"- effective_window: {manifest['effective_start_date']} to {manifest['effective_end_date']}",
        "",
        "## Row Counts",
        "",
        "```json",
        json.dumps(manifest["row_counts"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## Simulation Metrics",
        "",
    ]
    if metrics:
        lines.extend(["```json", json.dumps(metrics, ensure_ascii=False, indent=2), "```", ""])
    else:
        lines.extend(["simulation evaluation skipped", ""])
    if validation_summary:
        lines.extend(
            [
                "## Validation",
                "",
                f"- passed: {validation_summary['passed']}",
                f"- checks: {len(validation_summary['checks'])}",
                "",
            ]
        )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
