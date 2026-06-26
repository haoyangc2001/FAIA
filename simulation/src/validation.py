"""Run-level validation utilities for FAIA simulation outputs."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import yaml

from simulation.src.allocation import calculate_arrival_date, parse_date


InventoryKey = tuple[str, str, str]


def read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, sort_keys=False, allow_unicode=True)


def infer_repo_root(manifest_path: Path, manifest: dict[str, Any]) -> Path:
    config_path = Path(str(manifest.get("config", "")))
    candidates = [Path.cwd(), *manifest_path.resolve().parents]
    if config_path.is_absolute():
        return Path("/")
    for candidate in candidates:
        if (candidate / config_path).exists():
            return candidate
    return Path.cwd()


def resolve_path(path_text: str, repo_root: Path) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    return repo_root / path


def iter_csv_rows(path: Path) -> Iterable[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        yield from csv.DictReader(f)


def count_csv_rows(path: Path) -> int:
    with path.open("r", encoding="utf-8", newline="") as f:
        return sum(1 for _ in csv.DictReader(f))


def add_check(
    checks: list[dict[str, Any]],
    name: str,
    passed: bool,
    detail: str,
    metrics: dict[str, Any] | None = None,
) -> None:
    item: dict[str, Any] = {
        "name": name,
        "passed": bool(passed),
        "detail": detail,
    }
    if metrics is not None:
        item["metrics"] = metrics
    checks.append(item)


def file_entry(path: Path, rows: int | None = None) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "path": str(path),
        "bytes": path.stat().st_size if path.exists() else 0,
    }
    if rows is not None:
        entry["rows"] = rows
    return entry


def relative_file_entry(path: Path, repo_root: Path, rows: int | None = None) -> dict[str, Any]:
    entry = file_entry(path, rows=rows)
    entry["path"] = str(path.relative_to(repo_root))
    return entry


def write_stable_manifest(path: Path, manifest: dict[str, Any]) -> None:
    for _ in range(5):
        previous_entry = manifest["outputs"].get("simulation_manifest")
        write_yaml(path, manifest)
        current_entry = file_entry(path)
        manifest["outputs"]["simulation_manifest"] = current_entry
        if previous_entry == current_entry:
            break
    write_yaml(path, manifest)


def validate_simulation_run(
    manifest_path: Path,
    write_outputs: bool = True,
    update_manifest: bool = True,
) -> dict[str, Any]:
    """Validate one completed simulation run and optionally write validation artifacts."""

    manifest = read_yaml(manifest_path)
    repo_root = infer_repo_root(manifest_path, manifest)
    checks: list[dict[str, Any]] = []

    path_bundle = build_path_bundle(manifest, repo_root)
    validate_required_files(path_bundle, checks)
    validate_version_lineage(manifest, path_bundle, checks)
    validate_row_counts(manifest, path_bundle, checks)
    validate_non_negative_inventory(path_bundle, checks)
    fulfillment_metrics = validate_demand_conservation(path_bundle, checks)
    validate_transfer_constraints(manifest, path_bundle, checks)
    inventory_metrics = validate_inventory_conservation(manifest, path_bundle, checks)

    passed = all(check["passed"] for check in checks)
    summary = {
        "experiment_id": manifest["experiment_id"],
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "manifest_path": str(manifest_path),
        "passed": passed,
        "checks": checks,
        "metrics": {
            **fulfillment_metrics,
            **inventory_metrics,
        },
    }

    if write_outputs:
        run_dir = resolve_path(str(manifest["run_dir"]), repo_root)
        report_dir = repo_root / "simulation" / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        validation_summary_path = run_dir / "validation_summary.json"
        validation_report_path = report_dir / f"{manifest['experiment_id']}_validation_report.md"
        write_json(validation_summary_path, summary)
        write_validation_report(validation_report_path, summary)

        if update_manifest:
            manifest["validation"] = {
                "passed": passed,
                "checked_at": summary["checked_at"],
                "validation_summary": str(validation_summary_path.relative_to(repo_root)),
                "validation_report": str(validation_report_path.relative_to(repo_root)),
            }
            manifest["outputs"]["validation_summary"] = relative_file_entry(validation_summary_path, repo_root)
            manifest["outputs"]["validation_report"] = relative_file_entry(validation_report_path, repo_root)
            write_stable_manifest(manifest_path, manifest)
            summary["manifest_updated"] = True

    return summary


def build_path_bundle(manifest: dict[str, Any], repo_root: Path) -> dict[str, Path]:
    outputs = manifest["outputs"]
    inputs = manifest["inputs"]
    bundle = {
        "repo_root": repo_root,
        "config": resolve_path(str(manifest["config"]), repo_root),
        "rules": resolve_path(str(inputs["rules"]), repo_root),
        "policy": resolve_path(str(inputs["policy"]), repo_root),
        "warehouse_master": resolve_path(str(inputs["warehouse_master"]), repo_root),
        "transfer_plan": resolve_path(str(inputs["transfer_plan"]), repo_root),
        "inventory_daily_state": resolve_path(str(inputs["inventory_daily_state"]), repo_root),
        "candidate_pool_base": resolve_path(str(inputs["candidate_pool_base"]), repo_root),
        "daily_state": resolve_path(str(outputs["daily_state"]["path"]), repo_root),
        "transfer_result": resolve_path(str(outputs["transfer_result"]["path"]), repo_root),
        "fulfillment_result": resolve_path(str(outputs["fulfillment_result"]["path"]), repo_root),
        "cost_result": resolve_path(str(outputs["cost_result"]["path"]), repo_root),
        "metrics_summary": resolve_path(str(outputs["metrics_summary"]["path"]), repo_root),
        "daily_log": resolve_path(str(outputs["daily_log"]["path"]), repo_root),
        "simulation_config": resolve_path(str(outputs["simulation_config"]["path"]), repo_root),
    }
    return bundle


def validate_required_files(path_bundle: dict[str, Path], checks: list[dict[str, Any]]) -> None:
    missing = [
        name
        for name, path in path_bundle.items()
        if name != "repo_root" and not path.exists()
    ]
    add_check(
        checks,
        "required_files_exist",
        not missing,
        "all declared inputs and outputs exist" if not missing else f"missing files: {missing}",
        {"checked_files": len(path_bundle) - 1, "missing_files": len(missing)},
    )


def validate_version_lineage(
    manifest: dict[str, Any],
    path_bundle: dict[str, Path],
    checks: list[dict[str, Any]],
) -> None:
    expected = {
        "experiment_id": manifest["experiment_id"],
        "data_version": manifest["data_version"],
        "assortment_version": manifest["assortment_version"],
        "policy_version": manifest["policy_version"],
        "simulation_rule_version": manifest["simulation_rule_version"],
    }
    errors: list[str] = []

    lineage = manifest.get("version_lineage", {})
    for field, value in expected.items():
        if lineage.get(field) != value:
            errors.append(f"version_lineage.{field} mismatch")

    config = read_yaml(path_bundle["simulation_config"])
    for field, value in expected.items():
        if config.get(field) != value:
            errors.append(f"simulation_config.{field} mismatch")

    rules = read_yaml(path_bundle["rules"])
    if rules.get("simulation_rule_version") != expected["simulation_rule_version"]:
        errors.append("rules.simulation_rule_version mismatch")

    policy = read_yaml(path_bundle["policy"])
    if policy.get("policy_version") != expected["policy_version"]:
        errors.append("policy.policy_version mismatch")

    metrics_summary = read_json(path_bundle["metrics_summary"])
    for field, value in expected.items():
        if metrics_summary.get(field) != value:
            errors.append(f"metrics_summary.{field} mismatch")

    csv_errors = validate_csv_version_fields(
        [
            path_bundle["daily_state"],
            path_bundle["transfer_result"],
            path_bundle["fulfillment_result"],
            path_bundle["cost_result"],
        ],
        {
            "experiment_id": expected["experiment_id"],
            "data_version": expected["data_version"],
            "policy_version": expected["policy_version"],
            "simulation_rule_version": expected["simulation_rule_version"],
        },
    )
    errors.extend(csv_errors)

    add_check(
        checks,
        "version_lineage_consistent",
        not errors,
        "manifest, config, policy, rules, metrics and CSV outputs share one version lineage"
        if not errors
        else "; ".join(errors[:10]),
        {"error_count": len(errors)},
    )


def validate_csv_version_fields(paths: list[Path], expected: dict[str, str]) -> list[str]:
    errors: list[str] = []
    for path in paths:
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            missing_fields = sorted(set(expected) - set(reader.fieldnames or []))
            if missing_fields:
                errors.append(f"{path.name} missing version fields {missing_fields}")
                continue
            for index, row in enumerate(reader, start=1):
                for field, value in expected.items():
                    if row[field] != value:
                        errors.append(f"{path.name}:{index} {field} mismatch")
                        break
                if len(errors) >= 20:
                    return errors
    return errors


def validate_row_counts(
    manifest: dict[str, Any],
    path_bundle: dict[str, Path],
    checks: list[dict[str, Any]],
) -> None:
    actual = {
        "daily_state": count_csv_rows(path_bundle["daily_state"]),
        "transfer_result": count_csv_rows(path_bundle["transfer_result"]),
        "fulfillment_result": count_csv_rows(path_bundle["fulfillment_result"]),
        "cost_result": count_csv_rows(path_bundle["cost_result"]),
    }
    expected = manifest["row_counts"]
    errors = [name for name, value in actual.items() if int(expected[name]) != value]
    add_check(
        checks,
        "row_counts_match_manifest",
        not errors,
        "CSV row counts match simulation_manifest"
        if not errors
        else f"row count mismatch for: {errors}",
        {"actual": actual, "expected": expected},
    )


def validate_non_negative_inventory(path_bundle: dict[str, Path], checks: list[dict[str, Any]]) -> None:
    error_count = 0
    row_count = 0
    for row in iter_csv_rows(path_bundle["daily_state"]):
        row_count += 1
        on_hand = int(row["on_hand_qty"])
        reserved = int(row["reserved_qty"])
        in_transit = int(row["in_transit_qty"])
        available = int(row["available_qty"])
        position = int(row["inventory_position_qty"])
        if min(on_hand, reserved, in_transit, available, position) < 0:
            error_count += 1
        if available != max(0, on_hand - reserved):
            error_count += 1
        if position != available + in_transit:
            error_count += 1
    add_check(
        checks,
        "non_negative_inventory",
        error_count == 0,
        "all inventory quantities are non-negative and position fields are consistent"
        if error_count == 0
        else f"inventory validation errors: {error_count}",
        {"rows": row_count, "error_count": error_count},
    )


def validate_demand_conservation(path_bundle: dict[str, Path], checks: list[dict[str, Any]]) -> dict[str, Any]:
    totals = {
        "total_demand_qty": 0,
        "fdc_fulfilled_qty": 0,
        "rdc_fallback_qty": 0,
        "lost_sales_qty": 0,
    }
    error_count = 0
    row_count = 0
    for row in iter_csv_rows(path_bundle["fulfillment_result"]):
        row_count += 1
        demand = int(row["demand_qty"])
        fdc = int(row["fdc_fulfilled_qty"])
        rdc = int(row["rdc_fallback_qty"])
        lost = int(row["lost_sales_qty"])
        if min(demand, fdc, rdc, lost) < 0:
            error_count += 1
        if demand != fdc + rdc + lost:
            error_count += 1
        totals["total_demand_qty"] += demand
        totals["fdc_fulfilled_qty"] += fdc
        totals["rdc_fallback_qty"] += rdc
        totals["lost_sales_qty"] += lost

    metrics_summary = read_json(path_bundle["metrics_summary"])
    metric_errors = [
        name
        for name, value in totals.items()
        if int(metrics_summary[name]) != value
    ]
    passed = error_count == 0 and not metric_errors
    add_check(
        checks,
        "demand_conservation",
        passed,
        "fulfillment rows and metrics_summary satisfy demand conservation"
        if passed
        else f"row errors={error_count}, metric mismatches={metric_errors}",
        {"rows": row_count, "error_count": error_count, **totals},
    )
    return totals


def validate_transfer_constraints(
    manifest: dict[str, Any],
    path_bundle: dict[str, Path],
    checks: list[dict[str, Any]],
) -> None:
    rules = read_yaml(path_bundle["rules"])
    min_lead = int(rules["time"]["min_lead_time_days"])
    max_lead = int(rules["time"]["max_lead_time_days"])
    fdc_to_rdc = load_fdc_to_rdc(path_bundle["warehouse_master"])
    eligible_pairs = load_candidate_pairs(path_bundle["candidate_pool_base"])

    error_count = 0
    row_count = 0
    actual_transfer_qty = 0
    for row in iter_csv_rows(path_bundle["transfer_result"]):
        row_count += 1
        recommended = int(row["recommended_transfer_qty"])
        actual = int(row["actual_transfer_qty"])
        clipped = int(row["clipped_qty"])
        lead_time = int(row["lead_time_days"])
        if min(recommended, actual, clipped, lead_time) < 0:
            error_count += 1
        if actual > recommended:
            error_count += 1
        if clipped != max(0, recommended - actual):
            error_count += 1
        if row["arrival_date"] != calculate_arrival_date(row["ship_date"], lead_time):
            error_count += 1
        if lead_time < min_lead or lead_time > max_lead:
            error_count += 1
        if actual > 0:
            actual_transfer_qty += actual
            if fdc_to_rdc.get(row["fdc_id"]) != row["rdc_id"]:
                error_count += 1
            if (row["fdc_id"], row["sku_id"]) not in eligible_pairs:
                error_count += 1

    add_check(
        checks,
        "transfer_constraints",
        error_count == 0,
        "lead time, clipping, RDC-FDC relation and SKU-FDC eligibility constraints pass"
        if error_count == 0
        else f"transfer constraint errors: {error_count}",
        {
            "rows": row_count,
            "error_count": error_count,
            "actual_transfer_qty": actual_transfer_qty,
            "simulation_rule_version": manifest["simulation_rule_version"],
        },
    )


def validate_inventory_conservation(
    manifest: dict[str, Any],
    path_bundle: dict[str, Path],
    checks: list[dict[str, Any]],
) -> dict[str, Any]:
    initial_date = str(manifest["initial_inventory_date"])
    previous_state = load_initial_inventory(path_bundle["inventory_daily_state"], initial_date)
    transfer_arrivals, transfer_shipments, pipeline_events = load_transfer_movements(
        path_bundle["transfer_plan"],
        path_bundle["transfer_result"],
        initial_date,
    )
    fdc_consumption, rdc_consumption = load_fulfillment_consumption(path_bundle["fulfillment_result"])

    dates_checked = 0
    error_count = 0
    samples: list[dict[str, Any]] = []
    for simulation_date, actual_state, in_transit_state in iter_daily_state_by_date(path_bundle["daily_state"]):
        expected_state = defaultdict(int, previous_state)
        apply_inventory_delta(expected_state, transfer_arrivals.get(simulation_date, {}), sign=1)
        apply_inventory_delta(expected_state, transfer_shipments.get(simulation_date, {}), sign=-1)
        apply_inventory_delta(expected_state, fdc_consumption.get(simulation_date, {}), sign=-1)
        apply_inventory_delta(expected_state, rdc_consumption.get(simulation_date, {}), sign=-1)

        expected_in_transit = expected_pipeline_by_date(pipeline_events, simulation_date)
        mismatch_count, mismatch_samples = compare_inventory_maps(expected_state, actual_state)
        transit_mismatches = compare_in_transit_maps(expected_in_transit, in_transit_state)
        mismatch_count += len(transit_mismatches)
        if mismatch_count:
            error_count += mismatch_count
            samples.extend(
                {
                    "simulation_date": simulation_date,
                    **sample,
                }
                for sample in mismatch_samples[:5]
            )
            samples.extend(
                {
                    "simulation_date": simulation_date,
                    **sample,
                }
                for sample in transit_mismatches[:5]
            )
        previous_state = actual_state
        dates_checked += 1

    add_check(
        checks,
        "inventory_conservation",
        error_count == 0,
        "daily on-hand inventory and FDC in-transit quantities reconcile with arrivals, transfers and fulfillment"
        if error_count == 0
        else f"inventory conservation mismatches: {error_count}",
        {
            "dates_checked": dates_checked,
            "error_count": error_count,
            "sample_errors": samples[:10],
        },
    )
    return {
        "inventory_dates_checked": dates_checked,
        "inventory_conservation_errors": error_count,
    }


def load_fdc_to_rdc(path: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for row in iter_csv_rows(path):
        if row["node_type"] == "FDC":
            mapping[row["node_id"]] = row["rdc_id"]
    return mapping


def load_candidate_pairs(path: Path) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for row in iter_csv_rows(path):
        if row.get("eligible_flag", "true") == "true":
            pairs.add((row["fdc_id"], row["sku_id"]))
    return pairs


def load_initial_inventory(path: Path, initial_date: str) -> dict[InventoryKey, int]:
    state: dict[InventoryKey, int] = {}
    seen_date = False
    for row in iter_csv_rows(path):
        date = row["date"]
        if date == initial_date:
            key = (row["node_type"], row["node_id"], row["sku_id"])
            state[key] = int(row["on_hand_qty"])
            seen_date = True
        elif seen_date:
            break
    if not state:
        raise ValueError(f"no initial inventory rows for {initial_date}")
    return state


def load_transfer_movements(
    transfer_plan_path: Path,
    transfer_result_path: Path,
    initial_date: str,
) -> tuple[dict[str, dict[InventoryKey, int]], dict[str, dict[InventoryKey, int]], list[dict[str, Any]]]:
    arrivals: dict[str, dict[InventoryKey, int]] = defaultdict(lambda: defaultdict(int))
    shipments: dict[str, dict[InventoryKey, int]] = defaultdict(lambda: defaultdict(int))
    pipeline_events: list[dict[str, Any]] = []
    initial_dt = parse_date(initial_date)

    for row in iter_csv_rows(transfer_plan_path):
        ship_dt = parse_date(row["ship_date"])
        arrival_dt = parse_date(row["arrival_date"])
        if ship_dt <= initial_dt < arrival_dt:
            qty = int(row["transfer_qty"])
            arrival_key = ("FDC", row["fdc_id"], row["sku_id"])
            arrivals[row["arrival_date"]][arrival_key] += qty
            pipeline_events.append(
                {
                    "ship_date": row["ship_date"],
                    "arrival_date": row["arrival_date"],
                    "fdc_id": row["fdc_id"],
                    "sku_id": row["sku_id"],
                    "qty": qty,
                }
            )

    for row in iter_csv_rows(transfer_result_path):
        qty = int(row["actual_transfer_qty"])
        if qty <= 0:
            continue
        ship_key = ("RDC", row["rdc_id"], row["sku_id"])
        arrival_key = ("FDC", row["fdc_id"], row["sku_id"])
        shipments[row["ship_date"]][ship_key] += qty
        arrivals[row["arrival_date"]][arrival_key] += qty
        pipeline_events.append(
            {
                "ship_date": row["ship_date"],
                "arrival_date": row["arrival_date"],
                "fdc_id": row["fdc_id"],
                "sku_id": row["sku_id"],
                "qty": qty,
            }
        )
    return arrivals, shipments, pipeline_events


def load_fulfillment_consumption(
    fulfillment_path: Path,
) -> tuple[dict[str, dict[InventoryKey, int]], dict[str, dict[InventoryKey, int]]]:
    fdc_consumption: dict[str, dict[InventoryKey, int]] = defaultdict(lambda: defaultdict(int))
    rdc_consumption: dict[str, dict[InventoryKey, int]] = defaultdict(lambda: defaultdict(int))
    for row in iter_csv_rows(fulfillment_path):
        fdc_qty = int(row["fdc_fulfilled_qty"])
        rdc_qty = int(row["rdc_fallback_qty"])
        if fdc_qty:
            fdc_consumption[row["simulation_date"]][("FDC", row["fdc_id"], row["sku_id"])] += fdc_qty
        if rdc_qty:
            rdc_consumption[row["simulation_date"]][("RDC", row["rdc_id"], row["sku_id"])] += rdc_qty
    return fdc_consumption, rdc_consumption


def iter_daily_state_by_date(path: Path) -> Iterable[tuple[str, dict[InventoryKey, int], dict[tuple[str, str], int]]]:
    current_date = ""
    state: dict[InventoryKey, int] = {}
    in_transit: dict[tuple[str, str], int] = {}
    for row in iter_csv_rows(path):
        row_date = row["simulation_date"]
        if current_date and row_date != current_date:
            yield current_date, state, in_transit
            state = {}
            in_transit = {}
        current_date = row_date
        key = (row["node_type"], row["node_id"], row["sku_id"])
        state[key] = int(row["on_hand_qty"])
        if row["node_type"] == "FDC":
            in_transit[(row["node_id"], row["sku_id"])] = int(row["in_transit_qty"])
    if current_date:
        yield current_date, state, in_transit


def apply_inventory_delta(target: dict[InventoryKey, int], delta: dict[InventoryKey, int], sign: int) -> None:
    for key, qty in delta.items():
        target[key] += sign * qty


def compare_inventory_maps(
    expected: dict[InventoryKey, int],
    actual: dict[InventoryKey, int],
) -> tuple[int, list[dict[str, Any]]]:
    mismatch_count = 0
    samples: list[dict[str, Any]] = []
    for key in set(expected) | set(actual):
        expected_qty = int(expected.get(key, 0))
        actual_qty = int(actual.get(key, 0))
        if expected_qty != actual_qty:
            mismatch_count += 1
            if len(samples) < 10:
                samples.append(
                    {
                        "type": "on_hand_mismatch",
                        "node_type": key[0],
                        "node_id": key[1],
                        "sku_id": key[2],
                        "expected": expected_qty,
                        "actual": actual_qty,
                    }
                )
    return mismatch_count, samples


def expected_pipeline_by_date(
    pipeline_events: list[dict[str, Any]],
    simulation_date: str,
) -> dict[tuple[str, str], int]:
    date = parse_date(simulation_date)
    expected: dict[tuple[str, str], int] = defaultdict(int)
    for event in pipeline_events:
        ship_date = parse_date(event["ship_date"])
        arrival_date = parse_date(event["arrival_date"])
        if ship_date <= date < arrival_date:
            expected[(event["fdc_id"], event["sku_id"])] += int(event["qty"])
    return expected


def compare_in_transit_maps(
    expected: dict[tuple[str, str], int],
    actual: dict[tuple[str, str], int],
) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for key in set(expected) | set(actual):
        expected_qty = int(expected.get(key, 0))
        actual_qty = int(actual.get(key, 0))
        if expected_qty != actual_qty:
            samples.append(
                {
                    "type": "in_transit_mismatch",
                    "fdc_id": key[0],
                    "sku_id": key[1],
                    "expected": expected_qty,
                    "actual": actual_qty,
                }
            )
    return samples


def write_validation_report(path: Path, summary: dict[str, Any]) -> None:
    passed_text = "PASS" if summary["passed"] else "FAIL"
    lines = [
        f"# Simulation Validation Report: {summary['experiment_id']}",
        "",
        f"- checked_at: {summary['checked_at']}",
        f"- result: {passed_text}",
        f"- manifest_path: {summary['manifest_path']}",
        "",
        "## Checks",
        "",
    ]
    for check in summary["checks"]:
        status = "PASS" if check["passed"] else "FAIL"
        lines.extend(
            [
                f"### {check['name']}",
                "",
                f"- status: {status}",
                f"- detail: {check['detail']}",
                "",
                "```json",
                json.dumps(check.get("metrics", {}), ensure_ascii=False, indent=2),
                "```",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")
