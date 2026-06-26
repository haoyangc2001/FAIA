#!/usr/bin/env python3
"""Register a FAIA data version from generated manifests and validation output."""

from __future__ import annotations

import argparse
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


def read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def read_json_like_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_entry(path: Path, rows: int | None = None, checksum: bool = False) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "path": str(path),
        "bytes": path.stat().st_size,
    }
    if rows is not None:
        entry["rows"] = rows
    if checksum:
        entry["sha256"] = sha256_file(path)
    return entry


def build_table_entries(base_dir: Path, counts: dict[str, int]) -> list[dict[str, Any]]:
    entries = []
    for name, rows in counts.items():
        path = base_dir / f"{name}.csv"
        if path.exists():
            entries.append(file_entry(path, rows=rows))
    return entries


def upsert_registry(registry_path: Path, version_entry: dict[str, Any]) -> None:
    if registry_path.exists():
        registry = read_yaml(registry_path) or {}
    else:
        registry = {"versions": []}
    versions = [item for item in registry.get("versions", []) if item.get("data_version") != version_entry["data_version"]]
    versions.append(version_entry)
    versions.sort(key=lambda item: item["data_version"])
    registry["versions"] = versions
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    with registry_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(registry, f, sort_keys=False, allow_unicode=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Register FAIA data version.")
    parser.add_argument("--data-version", default="v001")
    parser.add_argument("--config", default="data/configs/synthetic_small.yaml")
    args = parser.parse_args()

    data_version = args.data_version
    config_path = Path(args.config)
    synthetic_dir = Path("data/synthetic") / data_version
    processed_dir = Path("data/processed") / data_version
    splits_dir = Path("data/splits") / data_version
    ml_dir = Path("data/features/ml_topk") / data_version
    inventory_dir = Path("data/features/inventory") / data_version
    validation_report = Path("data/validation/reports") / f"{data_version}_validation_report.md"
    validation_summary_path = Path("data/validation/reports") / f"{data_version}_validation_summary.json"
    version_dir = Path("data/versions") / data_version
    version_manifest_path = version_dir / "manifest.yaml"
    registry_path = Path("data/versions/version_registry.yaml")

    config = read_yaml(config_path)
    synthetic_manifest = read_yaml(synthetic_dir / "manifest.yaml")
    processed_manifest = read_yaml(processed_dir / "manifest.yaml")
    split_manifest = read_yaml(splits_dir / "manifest.yaml")
    ml_manifest = read_yaml(ml_dir / "manifest.yaml")
    inventory_manifest = read_yaml(inventory_dir / "manifest.yaml")
    validation_summary = read_json_like_yaml(validation_summary_path)

    control_files = [
        config_path,
        Path("data/scripts/generate_synthetic_data.py"),
        Path("data/scripts/build_stage1_artifacts.py"),
        Path("data/scripts/validate_stage1_data.py"),
        synthetic_dir / "manifest.yaml",
        processed_dir / "manifest.yaml",
        splits_dir / "manifest.yaml",
        ml_dir / "manifest.yaml",
        inventory_dir / "manifest.yaml",
        validation_summary_path,
        validation_report,
    ]

    manifest = {
        "data_version": data_version,
        "registered_at": datetime.now().isoformat(timespec="seconds"),
        "status": "validated" if validation_summary["overall_status"] == "PASS" else "validation_failed",
        "source": {
            "config": str(config_path),
            "seed": synthetic_manifest["seed"],
            "schema_version": synthetic_manifest["schema_version"],
            "generator_version": synthetic_manifest["generator_version"],
            "source_config_data_version": synthetic_manifest.get("source_config_data_version", config.get("data_version")),
        },
        "artifact_manifests": {
            "synthetic": str(synthetic_dir / "manifest.yaml"),
            "processed": str(processed_dir / "manifest.yaml"),
            "splits": str(splits_dir / "manifest.yaml"),
            "ml_topk_features": str(ml_dir / "manifest.yaml"),
            "inventory_features": str(inventory_dir / "manifest.yaml"),
        },
        "artifacts": {
            "synthetic": {
                "dir": str(synthetic_dir),
                "counts": synthetic_manifest["counts"],
                "files": build_table_entries(
                    synthetic_dir,
                    {k: v for k, v in synthetic_manifest["counts"].items() if k not in {"fdc_date_order_cells", "fdc_sku_date_demand_cells"}},
                ),
            },
            "processed": {
                "dir": str(processed_dir),
                "counts": processed_manifest["counts"],
                "files": build_table_entries(processed_dir, processed_manifest["counts"]),
            },
            "features": {
                "ml_topk": {
                    "dir": str(ml_dir),
                    "counts": ml_manifest["counts"],
                    "files": [file_entry(ml_dir / "fdc_sku_features.csv", rows=ml_manifest["counts"]["fdc_sku_features"])],
                },
                "inventory": {
                    "dir": str(inventory_dir),
                    "counts": inventory_manifest["counts"],
                    "files": [file_entry(inventory_dir / "inventory_features.csv", rows=inventory_manifest["counts"]["inventory_features"])],
                },
            },
            "splits": {
                "dir": str(splits_dir),
                "counts": split_manifest["counts"],
                "ranges": split_manifest["ranges"],
                "files": [
                    file_entry(splits_dir / "train_dates.txt", rows=split_manifest["counts"]["train_dates"]),
                    file_entry(splits_dir / "val_dates.txt", rows=split_manifest["counts"]["val_dates"]),
                    file_entry(splits_dir / "test_dates.txt", rows=split_manifest["counts"]["test_dates"]),
                ],
            },
        },
        "validation": {
            "status": validation_summary["overall_status"],
            "total_checks": validation_summary["total_checks"],
            "failed_checks": validation_summary["failed_checks"],
            "warnings": validation_summary["warnings"],
            "report": str(validation_report),
            "summary": str(validation_summary_path),
        },
        "reproducibility": {
            "commands": [
                f"python3 data/scripts/generate_synthetic_data.py --config {config_path} --data-version {data_version}",
                f"python3 data/scripts/build_stage1_artifacts.py --config {config_path} --data-version {data_version}",
                f"python3 data/scripts/validate_stage1_data.py --data-version {data_version}",
                f"python3 data/scripts/register_data_version.py --config {config_path} --data-version {data_version}",
            ]
        },
        "control_file_checksums": [
            file_entry(path, checksum=True) for path in control_files if path.exists()
        ],
    }

    version_dir.mkdir(parents=True, exist_ok=True)
    with version_manifest_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(manifest, f, sort_keys=False, allow_unicode=True)

    upsert_registry(
        registry_path,
        {
            "data_version": data_version,
            "status": manifest["status"],
            "registered_at": manifest["registered_at"],
            "manifest": str(version_manifest_path),
            "validation_report": str(validation_report),
            "config": str(config_path),
        },
    )

    print(yaml.safe_dump({"version_manifest": str(version_manifest_path), "registry": str(registry_path), "status": manifest["status"]}, sort_keys=False, allow_unicode=True))


if __name__ == "__main__":
    main()

