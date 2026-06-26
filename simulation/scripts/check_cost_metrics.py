#!/usr/bin/env python3
"""Smoke-check daily cost and metrics computation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from simulation.src.allocation import apply_arrivals
from simulation.src.cost import build_cost_records, cost_totals, load_cost_rates
from simulation.src.fulfillment import (
    fulfill_demands_for_date,
    fulfillment_totals,
    load_demand_for_date,
)
from simulation.src.initialization import initialize_simulation
from simulation.src.metrics import build_metrics_summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Check FAIA cost and metrics computation.")
    parser.add_argument("--config", default="simulation/configs/simulation_small.yaml")
    parser.add_argument("--simulation-date", default=None)
    args = parser.parse_args()

    init = initialize_simulation(Path(args.config))
    simulation_date = args.simulation_date or init.context.simulation_start_date
    apply_arrivals(init.state, simulation_date)
    demand_records = load_demand_for_date(init.input_paths.fdc_sku_daily_demand, simulation_date)
    fulfillment_records = fulfill_demands_for_date(
        simulation_date=simulation_date,
        demand_records=demand_records,
        state=init.state,
        context=init.context,
    )
    daily_state_rows = init.state.daily_state_rows(init.context)
    rates = load_cost_rates(init.input_paths.cost_config)
    cost_records = build_cost_records(
        simulation_date=simulation_date,
        fulfillment_records=fulfillment_records,
        transfer_results=[],
        daily_state_rows=daily_state_rows,
        rates=rates,
    )
    metrics = build_metrics_summary(
        context=init.context,
        fulfillment_records=fulfillment_records,
        cost_records=cost_records,
        simulation_start_date=simulation_date,
        simulation_end_date=simulation_date,
    )

    print(
        json.dumps(
            {
                "simulation_date": simulation_date,
                "fulfillment": fulfillment_totals(fulfillment_records),
                "cost_record_count": len(cost_records),
                "cost_totals": cost_totals(cost_records),
                "metrics_summary": metrics,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

