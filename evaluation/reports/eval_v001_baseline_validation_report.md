# Evaluation Validation Report: eval_v001_baseline

- passed: True
- checked_at: 2026-06-28T21:00:02
- manifest_path: evaluation/runs/eval_v001_baseline/evaluation_manifest.yaml
- failed_checks: 0

## Checks

### required_files_exist

- passed: True
- detail: all evaluation registry, metrics, comparison and report files exist
- metrics: {'missing_files': [], 'checked_files': 4}

### row_counts_match_manifest

- passed: True
- detail: CSV row counts match evaluation_manifest
- metrics: {'expected': {'experiment_registry': 4, 'metrics_summary': 638, 'comparison_table': 14}, 'actual': {'experiment_registry': 4, 'metrics_summary': 638, 'comparison_table': 14}}

### registry_protocol_consistent

- passed: True
- detail: registry rows share the evaluation protocol
- metrics: {'error_count': 0}

### metric_protocol_consistent

- passed: True
- detail: metric rows share the evaluation protocol
- metrics: {'error_count': 0}

### required_metrics_present

- passed: True
- detail: required evaluation metrics are present
- metrics: {'missing': []}

### metric_ranges_valid

- passed: True
- detail: metric values satisfy ratio and non-negative bounds
- metrics: {'error_count': 0}

### demand_conservation

- passed: True
- detail: operational demand metrics conserve total demand
- metrics: {'error_count': 0}

### cost_conservation

- passed: True
- detail: operational cost metrics conserve total cost
- metrics: {'error_count': 0}

### missing_artifacts_explicit

- passed: True
- detail: missing artifacts are explicitly represented with notes
- metrics: {'error_count': 0}
