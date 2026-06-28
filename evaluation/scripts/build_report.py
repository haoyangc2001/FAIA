#!/usr/bin/env python3
"""Build a Markdown report for a collected FAIA evaluation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from evaluation.src.report import build_evaluation_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build FAIA evaluation report.")
    parser.add_argument(
        "--manifest",
        default="evaluation/runs/eval_v001_baseline/evaluation_manifest.yaml",
        help="Path to evaluation_manifest.yaml.",
    )
    parser.add_argument(
        "--no-update-manifest",
        action="store_true",
        help="Write the report without adding it back to evaluation_manifest.yaml.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = build_evaluation_report(Path(args.manifest), update_manifest=not args.no_update_manifest)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

