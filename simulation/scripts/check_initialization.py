#!/usr/bin/env python3
"""Smoke-check simulation initialization."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from simulation.src.initialization import initialization_summary, initialize_simulation


def main() -> None:
    parser = argparse.ArgumentParser(description="Check FAIA simulation initialization.")
    parser.add_argument("--config", default="simulation/configs/simulation_small.yaml")
    args = parser.parse_args()

    init = initialize_simulation(Path(args.config))
    print(json.dumps(initialization_summary(init), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

