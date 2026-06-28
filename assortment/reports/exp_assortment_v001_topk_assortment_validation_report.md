# Assortment Validation Report: exp_assortment_v001_topk

- checked_at: 2026-06-28T20:59:06
- result: PASS
- manifest_path: assortment/runs/exp_assortment_v001_topk/assortment_manifest.yaml

## Checks

### date_window_valid

- status: PASS
- detail: anchor_date, effective_start_date and effective_end_date are ordered

```json
{}
```

### required_files_exist

- status: PASS
- detail: all required assortment files exist

```json
{
  "checked_files": 4,
  "missing_files": 0
}
```

### assortment_result_header

- status: PASS
- detail: assortment_result header matches schema

```json
{
  "field_count": 22
}
```

### row_counts_match_manifest

- status: PASS
- detail: assortment_result row count matches manifest

```json
{
  "expected": 3851,
  "actual": 3851
}
```

### assortment_result_rows_valid

- status: PASS
- detail: all assortment_result rows satisfy version, candidate and field constraints

```json
{
  "rows": 3851,
  "error_count": 0
}
```

### fdc_group_constraints

- status: PASS
- detail: each FDC has unique SKU rows and continuous rank within K

```json
{
  "fdc_count": 12,
  "total_selected_rows": 3851,
  "error_count": 0
}
```
