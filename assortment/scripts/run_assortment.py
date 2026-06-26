#!/usr/bin/env python3
"""Run the stage-3 assortment candidate, K, and Top-K baseline pipeline."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from assortment.src.candidate_pool import build_candidate_pool
from assortment.src.common import as_date_str, now_iso, read_yaml, write_yaml
from assortment.src.hybrid import build_hybrid_result
from assortment.src.k_selector import build_k_table
from assortment.src.reverse_exclude import build_reverse_exclude_result
from assortment.src.topk import build_topk_result


def run_assortment(config_path: Path) -> dict[str, object]:
    config = read_yaml(config_path)
    run_dir = Path(config["output"]["run_dir"])
    run_dir.mkdir(parents=True, exist_ok=True)

    candidate_summary = build_candidate_pool(config, run_dir)
    k_summary = build_k_table(config, run_dir)
    topk_summary = build_topk_result(config, run_dir)
    reverse_exclude_summary = build_reverse_exclude_result(config, run_dir)
    hybrid_summary = build_hybrid_result(config, run_dir)

    config_snapshot = run_dir / "assortment_config.yaml"
    shutil.copyfile(config_path, config_snapshot)

    manifest: dict[str, object] = {
        "experiment_id": config["experiment_id"],
        "data_version": config["data_version"],
        "candidate_pool_version": config["candidate_pool_version"],
        "k_rule_version": config["k_rule_version"],
        "method_version": config["method_version"],
        "assortment_version": config["assortment_version"],
        "method_versions": {
            "topk": config["method_version"],
            "reverse_exclude": config["reverse_exclude"]["method_version"],
            "hybrid": config["hybrid"]["method_version"],
        },
        "assortment_versions": {
            "topk": config["assortment_version"],
            "reverse_exclude": config["reverse_exclude"]["assortment_version"],
            "hybrid": config["hybrid"]["assortment_version"],
        },
        "anchor_date": as_date_str(config["anchor_date"]),
        "effective_start_date": as_date_str(config["effective_start_date"]),
        "effective_end_date": as_date_str(config["effective_end_date"]),
        "created_at": now_iso(),
        "run_dir": str(run_dir),
        "config_snapshot": str(config_snapshot),
        "row_counts": {
            "candidate_pool": candidate_summary["row_count"],
            "k_table": k_summary["row_count"],
            "topk_result": topk_summary["row_count"],
            "reverse_exclude_result": reverse_exclude_summary["row_count"],
            "hybrid_result": hybrid_summary["row_count"],
        },
        "candidate_summary": candidate_summary,
        "k_summary": k_summary,
        "topk_summary": topk_summary,
        "reverse_exclude_summary": reverse_exclude_summary,
        "hybrid_summary": hybrid_summary,
        "outputs": {
            "candidate_pool": str(run_dir / "candidate_pool.csv"),
            "k_table": str(run_dir / "k_table.csv"),
            "topk_result": str(run_dir / "topk_result.csv"),
            "reverse_exclude_result": str(run_dir / "reverse_exclude_result.csv"),
            "hybrid_result": str(run_dir / "hybrid_result.csv"),
            "run_manifest": str(run_dir / "run_manifest.yaml"),
        },
    }
    write_yaml(run_dir / "run_manifest.yaml", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Run FAIA assortment pipeline.")
    parser.add_argument("--config", default="assortment/configs/assortment_small.yaml")
    args = parser.parse_args()

    manifest = run_assortment(Path(args.config))
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
