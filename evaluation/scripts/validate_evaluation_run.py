#!/usr/bin/env python3
"""Validate a collected and reported FAIA evaluation run."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from evaluation.src.validation import validate_evaluation_run


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate FAIA evaluation run.")
    parser.add_argument(
        "--manifest",
        default="evaluation/runs/eval_v001_baseline/evaluation_manifest.yaml",
        help="Path to evaluation_manifest.yaml.",
    )
    parser.add_argument(
        "--no-update-manifest",
        action="store_true",
        help="Write validation artifacts without adding them back to evaluation_manifest.yaml.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = validate_evaluation_run(Path(args.manifest), update_manifest=not args.no_update_manifest)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not summary.get("passed"):
        sys.exit(1)


if __name__ == "__main__":
    main()
