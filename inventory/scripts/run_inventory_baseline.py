"""Run the inventory baseline chain from state to transfer recommendation."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from inventory.src.common import file_entry, read_yaml, write_yaml
from inventory.src.evaluator import run_inventory_simulation
from inventory.src.forecasting import build_demand_forecast_rows, write_demand_forecast
from inventory.src.manifest import build_inventory_manifest, write_inventory_manifest
from inventory.src.policies import generate_transfer_recommendation_rows, write_transfer_recommendation
from inventory.src.state_builder import build_inventory_state_rows, write_inventory_state
from inventory.src.tiss import build_tiss_rows, write_tiss_result
from inventory.src.validation import validate_inventory_run


def run_inventory_baseline(config_path: Path) -> dict[str, object]:
    config = read_yaml(config_path)
    run_dir = Path(str(config["output"]["run_dir"]))
    run_dir.mkdir(parents=True, exist_ok=True)

    state_rows = build_inventory_state_rows(config)
    state_path, state_count = write_inventory_state(config, state_rows)

    forecast_rows = build_demand_forecast_rows(config, state_rows)
    forecast_path, forecast_count = write_demand_forecast(config, forecast_rows)

    tiss_rows = build_tiss_rows(config, state_rows, forecast_rows)
    tiss_path, tiss_count = write_tiss_result(config, tiss_rows)

    transfer_rows = generate_transfer_recommendation_rows(config, state_rows, tiss_rows)
    transfer_path, transfer_count = write_transfer_recommendation(config, transfer_rows)

    row_counts = {
        "inventory_state": state_count,
        "demand_forecast": forecast_count,
        "tiss_result": tiss_count,
        "transfer_recommendation": transfer_count,
    }
    output_paths = {
        "inventory_state": state_path,
        "demand_forecast": forecast_path,
        "tiss_result": tiss_path,
        "transfer_recommendation": transfer_path,
    }

    simulation_summary = None
    if config.get("simulation", {}).get("enabled", False):
        simulation_summary = run_inventory_simulation(config, transfer_path)
        row_counts.update(simulation_summary["row_counts"])
        output_paths.update(simulation_summary["outputs"])

    manifest_path = run_dir / "inventory_manifest.yaml"
    manifest = build_inventory_manifest(
        config_path=config_path,
        config=config,
        row_counts=row_counts,
        output_paths=output_paths,
        simulation_summary=simulation_summary,
    )
    write_inventory_manifest(manifest_path, manifest)
    validation_summary = validate_inventory_run(manifest_path, write_outputs=True, update_manifest=True)

    summary = {
        "experiment_id": config["experiment_id"],
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "data_version": config["data_version"],
        "assortment_version": config["assortment_version"],
        "inventory_version": config["inventory_version"],
        "simulation_rule_version": config["simulation_rule_version"],
        "policy_name": config["policy"]["policy_name"],
        "policy_version": config["policy"]["policy_version"],
        "decision_date": config["decision_date"],
        "effective_start_date": config["effective_start_date"],
        "effective_end_date": config["effective_end_date"],
        "row_counts": row_counts,
        "outputs": {name: file_entry(path, rows=row_counts.get(name)) for name, path in output_paths.items()},
        "simulation_status": "completed" if simulation_summary else "skipped",
        "validation_status": "PASS" if validation_summary["passed"] else "FAIL",
        "manifest": str(manifest_path),
        "replay_command": f"PYTHONPATH=. python3 inventory/scripts/run_inventory_baseline.py --config {config_path}",
    }
    write_yaml(run_dir / "inventory_run_summary.yaml", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run FAIA inventory baseline.")
    parser.add_argument("--config", type=Path, default=Path("inventory/configs/inventory_small.yaml"))
    args = parser.parse_args()
    summary = run_inventory_baseline(args.config)
    print(summary)


if __name__ == "__main__":
    main()
