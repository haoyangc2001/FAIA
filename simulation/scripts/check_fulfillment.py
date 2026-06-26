#!/usr/bin/env python3
"""Smoke-check one-day fulfillment simulation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from simulation.src.allocation import apply_arrivals
from simulation.src.fulfillment import (
    fulfillment_totals,
    fulfill_demands_for_date,
    load_demand_for_date,
)
from simulation.src.initialization import initialize_simulation


def main() -> None:
    parser = argparse.ArgumentParser(description="Check FAIA one-day fulfillment behavior.")
    parser.add_argument("--config", default="simulation/configs/simulation_small.yaml")
    parser.add_argument("--simulation-date", default=None)
    args = parser.parse_args()

    init = initialize_simulation(Path(args.config))
    simulation_date = args.simulation_date or init.context.simulation_start_date
    before_fdc_inventory = sum(init.state.fdc_on_hand_inventory.values())
    before_rdc_inventory = sum(init.state.rdc_on_hand_inventory.values())
    arrivals = apply_arrivals(init.state, simulation_date)
    after_arrival_fdc_inventory = sum(init.state.fdc_on_hand_inventory.values())
    demand_records = load_demand_for_date(init.input_paths.fdc_sku_daily_demand, simulation_date)
    records = fulfill_demands_for_date(
        simulation_date=simulation_date,
        demand_records=demand_records,
        state=init.state,
        context=init.context,
    )
    after_fdc_inventory = sum(init.state.fdc_on_hand_inventory.values())
    after_rdc_inventory = sum(init.state.rdc_on_hand_inventory.values())
    totals = fulfillment_totals(records)

    print(
        json.dumps(
            {
                "simulation_date": simulation_date,
                "demand_cells": len(demand_records),
                "fulfillment_records": len(records),
                "arrival_events": len(arrivals),
                "arrival_qty": sum(event.qty for event in arrivals),
                "inventory": {
                    "fdc_before_arrivals": before_fdc_inventory,
                    "fdc_after_arrivals": after_arrival_fdc_inventory,
                    "fdc_after_fulfillment": after_fdc_inventory,
                    "rdc_before_fulfillment": before_rdc_inventory,
                    "rdc_after_fulfillment": after_rdc_inventory,
                },
                "totals": totals,
                "demand_conservation_ok": totals["demand_qty"]
                == totals["fdc_fulfilled_qty"] + totals["rdc_fallback_qty"] + totals["lost_sales_qty"],
                "fdc_inventory_consumed": after_arrival_fdc_inventory - after_fdc_inventory,
                "rdc_inventory_consumed": before_rdc_inventory - after_rdc_inventory,
                "lost_sales_cells": sum(1 for record in records if record.lost_sales_qty > 0),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

