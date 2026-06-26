# Simulation Report: sim_smoke_v001_no_transfer

- data_version: v001
- assortment_version: assortment_v001
- policy_version: no_transfer_v001
- simulation_rule_version: sim_rule_v001
- date_range: 2026-06-03 to 2026-06-29

## Metrics Summary

```json
{
  "experiment_id": "sim_smoke_v001_no_transfer",
  "data_version": "v001",
  "assortment_version": "assortment_v001",
  "policy_version": "no_transfer_v001",
  "simulation_rule_version": "sim_rule_v001",
  "simulation_start_date": "2026-06-03",
  "simulation_end_date": "2026-06-29",
  "total_demand_qty": 298426,
  "fdc_fulfilled_qty": 994,
  "rdc_fallback_qty": 13669,
  "lost_sales_qty": 283763,
  "fdc_fulfillment_rate": 0.00333081,
  "loss_ratio": 0.95086554,
  "transfer_cost": 0.0,
  "rdc_fallback_cost": 16402.8,
  "lost_sales_cost": 1418815.0,
  "holding_cost": 8946.78,
  "total_cost": 1444164.58
}
```

## Output Row Counts

```json
{
  "daily_state": 635310,
  "transfer_result": 0,
  "fulfillment_result": 99442,
  "cost_result": 179390
}
```

## Daily Log Sample

```json
{
  "first_days": [
    {
      "simulation_date": "2026-06-03",
      "arrival_events": 29,
      "arrival_qty": 57,
      "policy_decisions": 0,
      "recommended_transfer_qty": 0,
      "actual_transfer_qty": 0,
      "demand_cells": 3997,
      "demand_qty": 12054,
      "fdc_fulfilled_qty": 82,
      "rdc_fallback_qty": 868,
      "lost_sales_qty": 11104,
      "transfer_cost": 0.0,
      "rdc_fallback_cost": 1041.6,
      "lost_sales_cost": 55520.0,
      "holding_cost": 598.77,
      "total_cost": 57160.37
    },
    {
      "simulation_date": "2026-06-04",
      "arrival_events": 18,
      "arrival_qty": 36,
      "policy_decisions": 0,
      "recommended_transfer_qty": 0,
      "actual_transfer_qty": 0,
      "demand_cells": 4114,
      "demand_qty": 12462,
      "fdc_fulfilled_qty": 82,
      "rdc_fallback_qty": 1050,
      "lost_sales_qty": 11330,
      "transfer_cost": 0.0,
      "rdc_fallback_cost": 1260.0,
      "lost_sales_cost": 56650.0,
      "holding_cost": 565.89,
      "total_cost": 58475.89
    },
    {
      "simulation_date": "2026-06-05",
      "arrival_events": 5,
      "arrival_qty": 10,
      "policy_decisions": 0,
      "recommended_transfer_qty": 0,
      "actual_transfer_qty": 0,
      "demand_cells": 3790,
      "demand_qty": 11432,
      "fdc_fulfilled_qty": 70,
      "rdc_fallback_qty": 886,
      "lost_sales_qty": 10476,
      "transfer_cost": 0.0,
      "rdc_fallback_cost": 1063.2,
      "lost_sales_cost": 52380.0,
      "holding_cost": 537.51,
      "total_cost": 53980.71
    }
  ],
  "last_days": [
    {
      "simulation_date": "2026-06-27",
      "arrival_events": 0,
      "arrival_qty": 0,
      "policy_decisions": 0,
      "recommended_transfer_qty": 0,
      "actual_transfer_qty": 0,
      "demand_cells": 2917,
      "demand_qty": 8369,
      "fdc_fulfilled_qty": 18,
      "rdc_fallback_qty": 211,
      "lost_sales_qty": 8140,
      "transfer_cost": 0.0,
      "rdc_fallback_cost": 253.2,
      "lost_sales_cost": 40700.0,
      "holding_cost": 204.6,
      "total_cost": 41157.8
    },
    {
      "simulation_date": "2026-06-28",
      "arrival_events": 0,
      "arrival_qty": 0,
      "policy_decisions": 0,
      "recommended_transfer_qty": 0,
      "actual_transfer_qty": 0,
      "demand_cells": 3561,
      "demand_qty": 10645,
      "fdc_fulfilled_qty": 30,
      "rdc_fallback_qty": 279,
      "lost_sales_qty": 10336,
      "transfer_cost": 0.0,
      "rdc_fallback_cost": 334.8,
      "lost_sales_cost": 51680.0,
      "holding_cost": 195.33,
      "total_cost": 52210.13
    },
    {
      "simulation_date": "2026-06-29",
      "arrival_events": 0,
      "arrival_qty": 0,
      "policy_decisions": 0,
      "recommended_transfer_qty": 0,
      "actual_transfer_qty": 0,
      "demand_cells": 2985,
      "demand_qty": 8553,
      "fdc_fulfilled_qty": 17,
      "rdc_fallback_qty": 202,
      "lost_sales_qty": 8334,
      "transfer_cost": 0.0,
      "rdc_fallback_cost": 242.4,
      "lost_sales_cost": 41670.0,
      "holding_cost": 188.76,
      "total_cost": 42101.16
    }
  ]
}
```
