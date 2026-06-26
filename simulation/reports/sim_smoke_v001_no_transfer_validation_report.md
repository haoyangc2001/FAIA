# Simulation Validation Report: sim_smoke_v001_no_transfer

- checked_at: 2026-06-26T13:40:14
- result: PASS
- manifest_path: simulation/runs/sim_smoke_v001_no_transfer/simulation_manifest.yaml

## Checks

### required_files_exist

- status: PASS
- detail: all declared inputs and outputs exist

```json
{
  "checked_files": 14,
  "missing_files": 0
}
```

### version_lineage_consistent

- status: PASS
- detail: manifest, config, policy, rules, metrics and CSV outputs share one version lineage

```json
{
  "error_count": 0
}
```

### row_counts_match_manifest

- status: PASS
- detail: CSV row counts match simulation_manifest

```json
{
  "actual": {
    "daily_state": 635310,
    "transfer_result": 0,
    "fulfillment_result": 99442,
    "cost_result": 179390
  },
  "expected": {
    "daily_state": 635310,
    "transfer_result": 0,
    "fulfillment_result": 99442,
    "cost_result": 179390
  }
}
```

### non_negative_inventory

- status: PASS
- detail: all inventory quantities are non-negative and position fields are consistent

```json
{
  "rows": 635310,
  "error_count": 0
}
```

### demand_conservation

- status: PASS
- detail: fulfillment rows and metrics_summary satisfy demand conservation

```json
{
  "rows": 99442,
  "error_count": 0,
  "total_demand_qty": 298426,
  "fdc_fulfilled_qty": 994,
  "rdc_fallback_qty": 13669,
  "lost_sales_qty": 283763
}
```

### transfer_constraints

- status: PASS
- detail: lead time, clipping, RDC-FDC relation and SKU-FDC eligibility constraints pass

```json
{
  "rows": 0,
  "error_count": 0,
  "actual_transfer_qty": 0,
  "simulation_rule_version": "sim_rule_v001"
}
```

### inventory_conservation

- status: PASS
- detail: daily on-hand inventory and FDC in-transit quantities reconcile with arrivals, transfers and fulfillment

```json
{
  "dates_checked": 27,
  "error_count": 0,
  "sample_errors": []
}
```
