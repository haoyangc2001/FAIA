"""Publish a method result as the stable assortment_result interface."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any

from assortment.src.common import as_date_str, write_csv, write_yaml
from assortment.src.topk import TOPK_RESULT_FIELDS


ASSORTMENT_RESULT_FIELDS = TOPK_RESULT_FIELDS

METHOD_RESULT_FILES = {
    "topk": "topk_result.csv",
    "reverse_exclude": "reverse_exclude_result.csv",
    "hybrid": "hybrid_result.csv",
    "ml_topk": "ml_topk_result.csv",
}


def file_entry(path: Path, rows: int | None = None) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "path": str(path),
        "bytes": path.stat().st_size if path.exists() else 0,
    }
    if rows is not None:
        entry["rows"] = rows
    return entry


def _read_result_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        missing = sorted(set(ASSORTMENT_RESULT_FIELDS) - set(reader.fieldnames or []))
        if missing:
            raise ValueError(f"{path} missing result fields: {missing}")
        return list(reader)


def _report_dir(config: dict[str, Any], publish_cfg: dict[str, Any]) -> Path:
    configured = publish_cfg.get("report_dir") or config.get("output", {}).get("report_dir")
    return Path(str(configured or "assortment/reports"))


def publish_assortment_result(config: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    """Write stable assortment_result.csv and assortment_manifest.yaml."""

    publish_cfg = config.get("publish", {}) or {}
    method = str(publish_cfg.get("method", "hybrid"))
    if method not in METHOD_RESULT_FILES:
        raise ValueError(f"unsupported publish method: {method}")

    source_path = run_dir / METHOD_RESULT_FILES[method]
    if not source_path.exists():
        raise FileNotFoundError(f"publish source result not found: {source_path}")

    rows = _read_result_rows(source_path)
    if not rows:
        raise ValueError(f"publish source result is empty: {source_path}")

    output_path = run_dir / "assortment_result.csv"
    row_count = write_csv(output_path, ASSORTMENT_RESULT_FIELDS, rows)

    first = rows[0]
    manifest_path = run_dir / "assortment_manifest.yaml"
    metrics_path = run_dir / "assortment_metrics.json"
    report_dir = _report_dir(config, publish_cfg)
    report_path = report_dir / f"{config['experiment_id']}_assortment_report.md"
    validation_summary_path = run_dir / "assortment_validation_summary.json"
    validation_report_path = report_dir / f"{config['experiment_id']}_assortment_validation_report.md"

    manifest: dict[str, Any] = {
        "experiment_id": config["experiment_id"],
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "data_version": config["data_version"],
        "candidate_pool_version": config["candidate_pool_version"],
        "k_rule_version": config["k_rule_version"],
        "method": method,
        "method_version": first["method_version"],
        "assortment_version": first["assortment_version"],
        "anchor_date": as_date_str(config["anchor_date"]),
        "effective_start_date": as_date_str(config["effective_start_date"]),
        "effective_end_date": as_date_str(config["effective_end_date"]),
        "run_dir": str(run_dir),
        "publish_config": publish_cfg,
        "inputs": {
            "candidate_pool": str(run_dir / "candidate_pool.csv"),
            "k_table": str(run_dir / "k_table.csv"),
            "source_result": str(source_path),
            "config_snapshot": str(run_dir / "assortment_config.yaml"),
        },
        "outputs": {
            "assortment_result": file_entry(output_path, rows=row_count),
            "assortment_manifest": str(manifest_path),
            "assortment_metrics": str(metrics_path),
            "assortment_report": str(report_path),
            "validation_summary": str(validation_summary_path),
            "validation_report": str(validation_report_path),
        },
        "row_counts": {
            "assortment_result": row_count,
        },
        "version_lineage": {
            "experiment_id": config["experiment_id"],
            "data_version": config["data_version"],
            "candidate_pool_version": config["candidate_pool_version"],
            "k_rule_version": config["k_rule_version"],
            "method": method,
            "method_version": first["method_version"],
            "assortment_version": first["assortment_version"],
        },
        "replay_command": f"PYTHONPATH=. python3 assortment/scripts/run_assortment.py --config {publish_cfg.get('config_path', 'assortment/configs/assortment_small.yaml')}",
    }
    write_yaml(manifest_path, manifest)
    return {
        "method": method,
        "method_version": first["method_version"],
        "assortment_version": first["assortment_version"],
        "row_count": row_count,
        "assortment_result": str(output_path),
        "assortment_manifest": str(manifest_path),
    }
