# FAIA Logging and Error Handling Convention

This document defines the lightweight logging, reporting and failure behavior for project-level orchestration.

## Scope

The convention applies to root-level commands in `Makefile` and `scripts/run_full_pipeline.py`. Stage scripts may keep their local validation reports and stdout summaries, but root orchestration must make each stage command auditable from repository root.

## Run Logs

Project-level pipeline runs write logs under:

```text
artifacts/run_logs/
```

Each run writes two files:

```text
<run_id>.jsonl
Append-only event log. Each line is one JSON object.

<run_id>_summary.json
Final run summary with selected stages, step status, durations and expected output checks.
```

The default run id is:

```text
pipeline_YYYYMMDD_HHMMSS
```

Callers may override it:

```bash
PYTHONPATH=. python3 scripts/run_full_pipeline.py --run-id local_smoke --dry-run
```

## JSONL Events

The runner currently emits these event types:

```text
run_start
Written once before the first selected stage starts.

step_start
Written before each configured command.

step_finish
Written after each command or dry-run step.

run_finish
Written once at the end, including final status.
```

Every step event must include:

```text
stage
step
command
started_at
finished_at
duration_seconds
status
return_code
```

Executed steps also include bounded stdout and stderr tails:

```text
stdout_tail
stderr_tail
```

Tail length is configured in `configs/project.yaml` under:

```yaml
execution:
  stdout_tail_lines: 80
  stderr_tail_lines: 80
```

## Status Values

Runner status values:

```text
dry_run
Command was rendered and logged but not executed.

passed
Command returned exit code 0.

failed
Command returned a non-zero exit code.
```

Run summary status values:

```text
dry_run
All selected steps were rendered without execution.

passed
All selected executed steps returned exit code 0.

failed
At least one selected step returned a non-zero exit code.
```

## Failure Behavior

Default behavior is fail-fast:

```text
The first failed command stops the pipeline.
The failing stage and step are written to the summary.
The failing command stderr tail is printed to stderr.
```

Use this only when deliberately collecting multiple failures:

```bash
PYTHONPATH=. python3 scripts/run_full_pipeline.py --continue-on-error
```

## Reports

Stage-specific reports stay in each stage directory:

```text
data/validation/reports/
assortment/reports/
simulation/reports/
inventory/reports/
evaluation/reports/
```

Root orchestration does not rewrite those reports. It records the commands and output checks needed to trace them.

## Expected Output Checks

After an executed stage finishes, the runner checks that stage `expected_outputs` from `configs/project.yaml` exist. These checks are written to summary JSON as `stage_outputs`.

Expected output checks are informational in the current runner. Stage validation scripts remain the source of truth for PASS/FAIL decisions.

## Missing Artifacts

Known missing artifacts must be explicit in evaluation registries and reports. If a declared upstream manifest is absent, evaluation records that as `missing` or `not_run` instead of ignoring the declared experiment.

Current v001 acceptance has no missing upstream runs:

```text
latest_run_id: pipeline_20260628_204301
evaluation_id: eval_v001_baseline
available_runs: 4
missing_runs: 0
evaluation_validation_failed_checks: 0
```

## Developer Rules

When adding a new root-level command or stage:

```text
Add it to configs/project.yaml.
Declare expected_outputs.
Ensure the first command element is {python} or another explicit executable.
Ensure all script paths exist from repository root.
Record stable output paths in the relevant manifest.
Add or update integration tests if the command changes root orchestration behavior.
```
