"""Markdown report generation for FAIA evaluation runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from evaluation.src.common import file_entry, infer_repo_root, output_path, read_csv_rows, read_yaml, relative_path, resolve_path, to_text, write_yaml


def build_evaluation_report(manifest_path: Path, update_manifest: bool = True) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    repo_root = infer_repo_root(manifest_path)
    manifest = read_yaml(manifest_path)

    registry_path = manifest_output_path(manifest, "experiment_registry", repo_root)
    metrics_path = manifest_output_path(manifest, "metrics_summary", repo_root)
    comparison_path = manifest_output_path(manifest, "comparison_table", repo_root)
    report_path = resolve_path(
        output_path(manifest.get("expected_outputs", {}).get("evaluation_report", ""))
        or f"evaluation/reports/{manifest['evaluation_id']}_report.md",
        repo_root,
    )

    registry = read_csv_rows(registry_path)
    metrics = read_csv_rows(metrics_path)
    comparison = read_csv_rows(comparison_path)

    lines = render_report(manifest, registry, metrics, comparison)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    summary = {
        "evaluation_id": manifest["evaluation_id"],
        "report_path": relative_path(report_path, repo_root),
        "registry_rows": len(registry),
        "metrics_rows": len(metrics),
        "comparison_rows": len(comparison),
        "sections": [
            "protocol",
            "registry",
            "data_metrics",
            "comparison",
            "tradeoff",
            "anomalies",
            "conclusion",
        ],
    }
    if update_manifest:
        manifest.setdefault("outputs", {})
        manifest["outputs"]["evaluation_report"] = file_entry(report_path, repo_root)
        if manifest.get("status") == "collected":
            manifest["status"] = "reported"
        write_yaml(manifest_path, manifest)
    return summary


def manifest_output_path(manifest: dict[str, Any], name: str, repo_root: Path) -> Path:
    outputs = manifest.get("outputs", {})
    expected = manifest.get("expected_outputs", {})
    raw = output_path(outputs.get(name, "")) or output_path(expected.get(name, ""))
    if not raw:
        raise ValueError(f"evaluation manifest missing output path for {name}")
    return resolve_path(raw, repo_root)


def render_report(
    manifest: dict[str, Any],
    registry: list[dict[str, str]],
    metrics: list[dict[str, str]],
    comparison: list[dict[str, str]],
) -> list[str]:
    protocol = manifest["protocol"]
    collection = manifest.get("collection_summary", {})
    lines = [
        f"# Evaluation Report: {manifest['evaluation_id']}",
        "",
        "## Experiment Goal",
        "",
        "Compare the available v001 data, assortment, simulation and inventory artifacts under one fixed evaluation protocol.",
        "",
        "## Protocol",
        "",
        f"- evaluation_version: {manifest['evaluation_version']}",
        f"- data_version: {protocol['data_version']}",
        f"- split_version: {protocol['split_version']}",
        f"- evaluation_split: {protocol['evaluation_split']}",
        f"- evaluation_window: {protocol['evaluation_window']['start_date']} to {protocol['evaluation_window']['end_date']}",
        f"- assortment_version: {protocol.get('assortment_version', '')}",
        f"- inventory_version: {protocol.get('inventory_version', '')}",
        f"- simulation_rule_version: {protocol.get('simulation_rule_version', '')}",
        f"- cost_config_version: {protocol.get('cost_config_version', '')}",
        "",
        "## Registry",
        "",
        f"- available_runs: {collection.get('available_runs', count_rows(registry, 'run_status', 'available'))}",
        f"- missing_runs: {collection.get('missing_runs', count_rows(registry, 'run_status', 'missing'))}",
        f"- metric_rows_by_stage: {collection.get('metric_rows_by_stage', metric_rows_by_stage(metrics))}",
        "",
        "| stage | experiment_id | status | method | validation | notes |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in registry:
        lines.append(
            "| {stage} | {experiment_id} | {run_status} | {method_name} | {validation_status} | {notes} |".format(
                **clean_row(row)
            )
        )

    lines.extend(
        [
            "",
            "## Data Metrics",
            "",
            "| metric | value |",
            "| --- | ---: |",
        ]
    )
    for name in [
        "num_orders",
        "num_order_items",
        "num_skus",
        "num_warehouses",
        "candidate_pool_rows",
        "inventory_daily_state_rows",
        "validation_error_count",
    ]:
        lines.append(f"| {name} | {metric_value(metrics, 'data', '', name)} |")

    lines.extend(
        [
            "",
            "## Main Comparison",
            "",
            "| type | id | status | metrics | selected_sku_count | fdc_fulfillment_rate | loss_ratio | lost_sales_qty | transfer_cost | total_cost | notes |",
            "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in comparison:
        lines.append(
            "| {comparison_type} | {comparison_id} | {run_status} | {metrics_status} | {selected_sku_count} | {fdc_fulfillment_rate} | {loss_ratio} | {lost_sales_qty} | {transfer_cost} | {total_cost} | {notes} |".format(
                **clean_row(row)
            )
        )

    lines.extend(["", "## Trade-Off Analysis", ""])
    lines.extend(tradeoff_lines(comparison))
    lines.extend(["", "## Anomaly Analysis", ""])
    lines.extend(anomaly_lines(registry, comparison))
    lines.extend(["", "## Conclusion", ""])
    lines.extend(conclusion_lines(registry, comparison))
    return lines


def clean_row(row: dict[str, str]) -> dict[str, str]:
    return {key: value.replace("|", "/") for key, value in row.items()}


def count_rows(rows: list[dict[str, str]], field: str, value: str) -> int:
    return sum(1 for row in rows if row.get(field) == value)


def metric_rows_by_stage(metrics: list[dict[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in metrics:
        stage = row.get("stage", "")
        counts[stage] = counts.get(stage, 0) + 1
    return counts


def metric_value(metrics: list[dict[str, str]], stage: str, method_name: str, metric_name: str) -> str:
    for row in metrics:
        if row.get("stage") != stage or row.get("metric_name") != metric_name:
            continue
        if method_name and row.get("method_name") != method_name:
            continue
        if row.get("metric_level") == "overall":
            return row.get("metric_value", "")
    return ""


def tradeoff_lines(comparison: list[dict[str, str]]) -> list[str]:
    available = [row for row in comparison if row.get("comparison_type") == "inventory_method" and row.get("metrics_status") == "available"]
    if not available:
        return ["- No inventory method has complete operational metrics yet."]
    lines = []
    for row in available:
        lines.append(
            "- {method}: fdc_fulfillment_rate={fdc}, loss_ratio={loss}, transfer_cost={transfer}, total_cost={total}.".format(
                method=row.get("method_name", ""),
                fdc=row.get("fdc_fulfillment_rate", ""),
                loss=row.get("loss_ratio", ""),
                transfer=row.get("transfer_cost", ""),
                total=row.get("total_cost", ""),
            )
        )
    if len(available) == 1:
        lines.append("- Only one operational baseline is currently available, so cost/service trade-offs are directional rather than comparative.")
    return lines


def anomaly_lines(registry: list[dict[str, str]], comparison: list[dict[str, str]]) -> list[str]:
    lines: list[str] = []
    for row in registry:
        if row.get("run_status") in {"missing", "not_run", "invalid"}:
            lines.append(f"- {row.get('stage')} {row.get('experiment_id')}: {row.get('notes')}")
    partial = [row for row in comparison if row.get("metrics_status") in {"partial", "missing"}]
    if partial:
        lines.append(f"- {len(partial)} comparison rows have partial or missing metrics.")
    if not lines:
        lines.append("- No missing or partial experiment artifacts detected.")
    return lines


def conclusion_lines(registry: list[dict[str, str]], comparison: list[dict[str, str]]) -> list[str]:
    inventory_missing = any(row.get("stage") == "inventory" and row.get("run_status") == "missing" for row in registry)
    no_transfer = next((row for row in comparison if row.get("comparison_id") == "no_transfer"), None)
    lines = []
    if no_transfer and no_transfer.get("metrics_status") == "available":
        lines.append(
            f"- Current operational baseline is no_transfer with fdc_fulfillment_rate={no_transfer.get('fdc_fulfillment_rate')} and total_cost={no_transfer.get('total_cost')}."
        )
    if inventory_missing:
        lines.append("- Inventory allocation comparison is blocked until the declared inventory run manifest is produced.")
    lines.append("- Next step is to add complete inventory and assortment metric runs for richer trade-off analysis.")
    return lines
