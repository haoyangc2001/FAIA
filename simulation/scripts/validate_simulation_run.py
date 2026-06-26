"""Validate one completed FAIA simulation run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from simulation.src.validation import validate_simulation_run


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        default="simulation/runs/sim_smoke_v001_no_transfer/simulation_manifest.yaml",
        help="Path to simulation_manifest.yaml.",
    )
    parser.add_argument(
        "--no-update-manifest",
        action="store_true",
        help="Write validation artifacts without adding them back to simulation_manifest.yaml.",
    )
    args = parser.parse_args()

    summary = validate_simulation_run(
        Path(args.manifest),
        write_outputs=True,
        update_manifest=not args.no_update_manifest,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not summary["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
