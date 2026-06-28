#!/usr/bin/env python3
"""Validate a published FAIA assortment run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from assortment.src.validation import validate_assortment_run


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate FAIA assortment run outputs.")
    parser.add_argument(
        "--manifest",
        default="assortment/runs/exp_assortment_v001_topk/assortment_manifest.yaml",
        help="Path to assortment_manifest.yaml.",
    )
    parser.add_argument("--no-update-manifest", action="store_true")
    args = parser.parse_args()

    summary = validate_assortment_run(
        Path(args.manifest),
        write_outputs=True,
        update_manifest=not args.no_update_manifest,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not summary["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
