#!/usr/bin/env python3
"""Collect FAIA evaluation registry, metrics and comparison tables."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from evaluation.src.collect import collect_results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect FAIA evaluation artifacts.")
    parser.add_argument(
        "--config",
        default="evaluation/configs/evaluation_default.yaml",
        help="Path to evaluation config.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = collect_results(Path(args.config))
    print(
        json.dumps(
            {
                "evaluation_id": manifest["evaluation_id"],
                "status": manifest["status"],
                "row_counts": manifest["row_counts"],
                "collection_summary": manifest["collection_summary"],
                "outputs": manifest["outputs"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

