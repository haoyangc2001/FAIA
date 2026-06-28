"""Validate one inventory allocation run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from inventory.src.validation import validate_inventory_run


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate FAIA inventory run outputs.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("inventory/runs/exp_inventory_v001_base_stock/inventory_manifest.yaml"),
    )
    args = parser.parse_args()
    summary = validate_inventory_run(args.manifest)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not summary["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
