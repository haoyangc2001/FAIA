# FAIA Manifest Standards

This document defines the project-level manifest and version conventions used by the FAIA data, simulation, assortment, inventory and evaluation stages.

## Goals

Manifests are the stable contracts between stages. Every stage run should be reproducible from its manifest without guessing which input data, config, method, rule or output files were used.

The manifest standard has four goals:

```text
traceability
Every published artifact can be traced back to data_version, config, method/rule version and experiment_id.

replayability
Every completed run records the command needed to reproduce it.

comparability
Evaluation only compares runs that share the required data, split, simulation rule and cost protocol.

explicit gaps
Missing or not-yet-run experiments are represented explicitly in evaluation, never silently skipped.
```

## Required Fields

Every stage manifest should include the fields below when they apply to that stage.

```text
experiment_id
Unique run identifier for a stage experiment. Data version manifests may use data_version as the experiment identifier in registries.

created_at
Local timestamp when the manifest was written.

status
Lifecycle status such as generated, completed, validated, missing, planned or failed.

config
Path to the YAML config or a config snapshot used to produce the run.

run_dir
Directory containing the run outputs.

inputs
Input files or upstream manifests consumed by this run.

outputs
Output files produced by this run. Stable cross-stage outputs should be named explicitly.

row_counts
Row counts for CSV outputs and countable artifacts.

validation
Validation status, summary path, report path and failed check count when available.

replay_command
Shell command to reproduce the run from repository root.
```

## Version Fields

Version fields are shared across stages and should use stable string values.

```text
data_version
Synthetic/raw/processed data version. Current default: v001.

split_version
Time split version used for train, validation and test windows. Current default: split_v001.

feature_version
Feature artifact version when model or policy features are materialized separately.

candidate_pool_version
Candidate SKU-FDC pool version used by assortment. Current default: candidate_pool_v001.

k_rule_version
Assortment K selection rule version. Current default: k_rule_v001.

assortment_version
Published FDC-SKU assortment version consumed by downstream inventory and evaluation.

method_version
Algorithm or heuristic method version inside a stage, such as topk_v001 or hybrid_v001.

model_version
Model artifact version. Use none when a rule baseline has no trained model.

policy_version
Simulation or inventory policy version.

inventory_version
Published inventory allocation strategy version.

simulation_rule_version
Business simulation rule version used for replay and evaluation.

cost_config_version
Cost protocol version. Current first version is represented by the v001 cost_config path.

evaluation_id
Unified evaluation run identifier.

evaluation_version
Evaluation protocol version.
```

## Stage-Specific Stable Outputs

The current stable cross-stage outputs are:

```text
data
data/versions/<data_version>/manifest.yaml
data/processed/<data_version>/manifest.yaml
data/splits/<data_version>/manifest.yaml

assortment
assortment/runs/<experiment_id>/assortment_manifest.yaml
assortment/runs/<experiment_id>/assortment_result.csv

simulation
simulation/runs/<experiment_id>/simulation_manifest.yaml
simulation/runs/<experiment_id>/metrics_summary.json

inventory
inventory/runs/<experiment_id>/inventory_manifest.yaml
inventory/runs/<experiment_id>/transfer_recommendation.csv

evaluation
evaluation/runs/<evaluation_id>/evaluation_manifest.yaml
evaluation/runs/<evaluation_id>/experiment_registry.csv
evaluation/runs/<evaluation_id>/metrics_summary.csv
evaluation/runs/<evaluation_id>/comparison_table.csv
```

## Status Values

Use these status values consistently:

```text
planned
Declared in a protocol or baseline matrix but not expected to exist yet.

missing
Expected by a protocol but the manifest or output file is absent.

generated
Produced by a stage but not yet fully validated.

completed
Stage run finished successfully.

validated
Stage run passed validation and validation artifacts were written.

failed
Stage run or validation failed.
```

## Evaluation Comparability

A single evaluation run must keep these fields consistent for comparable rows:

```text
data_version
split_version
evaluation_window
simulation_rule_version
cost_config_version
```

Evaluation may include missing or planned experiments, but those rows must carry an explicit status and note. Missing experiments must not contribute operational comparison metrics.

## Current V001 Acceptance Snapshot

The latest accepted project-level run is:

```text
run_id: pipeline_20260628_204301
status: passed
selected_stages: data, assortment, simulation, inventory, evaluation
steps: 14
missing_stage_outputs: 0
```

The default v001 manifest chain is:

```text
data/versions/v001/manifest.yaml
assortment/runs/exp_assortment_v001_topk/assortment_manifest.yaml
simulation/runs/sim_smoke_v001_no_transfer/simulation_manifest.yaml
inventory/runs/exp_inventory_v001_base_stock/inventory_manifest.yaml
evaluation/runs/eval_v001_baseline/evaluation_manifest.yaml
```

Evaluation registry status for this run is:

```text
data: available / PASS
assortment: available / PASS
simulation: available / PASS
inventory: available / PASS
```

## Current Known Compatibility Note

The current no-transfer simulation smoke run records `assortment_version: assortment_v001`, while the first published assortment protocol uses `assortment_hybrid_v001`. Evaluation treats that simulation as an operational no-transfer baseline, not as a matched assortment-inventory combination. Future simulation runs should consume the published assortment version directly when method comparisons require strict version matching.
