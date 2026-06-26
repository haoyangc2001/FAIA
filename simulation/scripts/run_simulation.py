#!/usr/bin/env python3
"""Run FAIA business simulation and write replay outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from simulation.src.engine import run_simulation


def main() -> None:
    parser = argparse.ArgumentParser(description="Run FAIA simulation.")
    parser.add_argument("--config", default="simulation/configs/simulation_small.yaml")
    args = parser.parse_args()

    manifest = run_simulation(Path(args.config))
    print(
        json.dumps(
            {
                "experiment_id": manifest["experiment_id"],
                "run_dir": manifest["run_dir"],
                "data_version": manifest["data_version"],
                "assortment_version": manifest["assortment_version"],
                "policy_version": manifest["policy_version"],
                "simulation_rule_version": manifest["simulation_rule_version"],
                "row_counts": manifest["row_counts"],
                "metrics_summary": manifest["metrics_summary"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
