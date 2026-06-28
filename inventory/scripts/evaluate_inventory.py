"""Run simulation evaluation for an existing inventory baseline output."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from inventory.src.common import read_yaml
from inventory.src.evaluator import run_inventory_simulation


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate inventory transfer recommendations with simulation.")
    parser.add_argument("--config", type=Path, default=Path("inventory/configs/inventory_small.yaml"))
    parser.add_argument("--transfer-recommendation", type=Path, default=None)
    args = parser.parse_args()
    config = read_yaml(args.config)
    transfer_path = args.transfer_recommendation or Path(str(config["output"]["run_dir"])) / "transfer_recommendation.csv"
    summary = run_inventory_simulation(config, transfer_path)
    print(json.dumps(summary["metrics_summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
