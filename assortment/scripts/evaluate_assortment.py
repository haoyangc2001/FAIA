#!/usr/bin/env python3
"""Evaluate existing assortment run outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from assortment.src.common import read_yaml
from assortment.src.evaluation import evaluate_assortment


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate FAIA assortment outputs.")
    parser.add_argument("--config", default="assortment/configs/assortment_small.yaml")
    args = parser.parse_args()

    config = read_yaml(Path(args.config))
    run_dir = Path(config["output"]["run_dir"])
    summary = evaluate_assortment(config, run_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
