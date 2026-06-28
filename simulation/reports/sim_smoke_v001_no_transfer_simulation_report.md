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
  "fdc_fulfilled_qty": 1000,
  "rdc_fallback_qty": 13637,
  "lost_sales_qty": 283789,
  "fdc_fulfillment_rate": 0.00335091,
  "loss_ratio": 0.95095266,
  "transfer_cost": 0.0,
  "rdc_fallback_cost": 16364.4,
  "lost_sales_cost": 1418945.0,
  "holding_cost": 8931.66,
  "total_cost": 1444241.06
}
```

## Output Row Counts

```json
{
  "daily_state": 635310,
  "transfer_result": 0,
  "fulfillment_result": 99442,
  "cost_result": 179300
}
```

## Daily Log Sample

```json
{
  "first_days": [
    {
      "simulation_date": "2026-06-03",
      "arrival_events": 26,
      "arrival_qty": 55,
      "policy_decisions": 0,
      "recommended_transfer_qty": 0,
      "actual_transfer_qty": 0,
      "demand_cells": 3997,
      "demand_qty": 12054,
      "fdc_fulfilled_qty": 84,
      "rdc_fallback_qty": 861,
      "lost_sales_qty": 11109,
      "transfer_cost": 0.0,
      "rdc_fallback_cost": 1033.2,
      "lost_sales_cost": 55545.0,
      "holding_cost": 597.39,
      "total_cost": 57175.59
    },
    {
      "simulation_date": "2026-06-04",
      "arrival_events": 23,
      "arrival_qty": 48,
      "policy_decisions": 0,
      "recommended_transfer_qty": 0,
      "actual_transfer_qty": 0,
      "demand_cells": 4114,
      "demand_qty": 12462,
      "fdc_fulfilled_qty": 85,
      "rdc_fallback_qty": 1050,
      "lost_sales_qty": 11327,
      "transfer_cost": 0.0,
      "rdc_fallback_cost": 1260.0,
      "lost_sales_cost": 56635.0,
      "holding_cost": 564.78,
      "total_cost": 58459.78
    },
    {
      "simulation_date": "2026-06-05",
      "arrival_events": 6,
      "arrival_qty": 11,
      "policy_decisions": 0,
      "recommended_transfer_qty": 0,
      "actual_transfer_qty": 0,
      "demand_cells": 3790,
      "demand_qty": 11432,
      "fdc_fulfilled_qty": 76,
      "rdc_fallback_qty": 883,
      "lost_sales_qty": 10473,
      "transfer_cost": 0.0,
      "rdc_fallback_cost": 1059.6,
      "lost_sales_cost": 52365.0,
      "holding_cost": 536.34,
      "total_cost": 53960.94
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
      "fdc_fulfilled_qty": 17,
      "rdc_fallback_qty": 211,
      "lost_sales_qty": 8141,
      "transfer_cost": 0.0,
      "rdc_fallback_cost": 253.2,
      "lost_sales_cost": 40705.0,
      "holding_cost": 204.21,
      "total_cost": 41162.41
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
      "fdc_fulfilled_qty": 28,
      "rdc_fallback_qty": 280,
      "lost_sales_qty": 10337,
      "transfer_cost": 0.0,
      "rdc_fallback_cost": 336.0,
      "lost_sales_cost": 51685.0,
      "holding_cost": 194.97,
      "total_cost": 52215.97
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
      "holding_cost": 188.4,
      "total_cost": 42100.8
    }
  ]
}
```
