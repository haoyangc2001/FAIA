"""Run-level validation for published assortment outputs."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import yaml

from assortment.src.common import as_bool, as_date_str, as_int
from assortment.src.publish import ASSORTMENT_RESULT_FIELDS, file_entry


ALLOWED_SOURCE_TAGS = {"topk", "reverse_exclude", "hybrid", "ml_topk", "forced_include", "baseline"}


def read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, sort_keys=False, allow_unicode=True)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def iter_csv_rows(path: Path) -> Iterable[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        yield from csv.DictReader(f)


def count_csv_rows(path: Path) -> int:
    with path.open("r", encoding="utf-8", newline="") as f:
        return sum(1 for _ in csv.DictReader(f))


def resolve_path(path_text: str, base_dir: Path) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    return base_dir / path


def manifest_output_path(value: Any) -> str:
    if isinstance(value, dict):
        return str(value["path"])
    return str(value)


def add_check(
    checks: list[dict[str, Any]],
    name: str,
    passed: bool,
    detail: str,
    metrics: dict[str, Any] | None = None,
) -> None:
    check: dict[str, Any] = {
        "name": name,
        "passed": bool(passed),
        "detail": detail,
    }
    if metrics is not None:
        check["metrics"] = metrics
    checks.append(check)


def validate_date_window(manifest: dict[str, Any], checks: list[dict[str, Any]]) -> None:
    anchor = datetime.strptime(as_date_str(manifest["anchor_date"]), "%Y-%m-%d")
    effective_start = datetime.strptime(as_date_str(manifest["effective_start_date"]), "%Y-%m-%d")
    effective_end = datetime.strptime(as_date_str(manifest["effective_end_date"]), "%Y-%m-%d")
    passed = anchor < effective_start <= effective_end
    add_check(
        checks,
        "date_window_valid",
        passed,
        "anchor_date, effective_start_date and effective_end_date are ordered"
        if passed
        else "expected anchor_date < effective_start_date <= effective_end_date",
    )


def validate_required_files(manifest: dict[str, Any], base_dir: Path, checks: list[dict[str, Any]]) -> dict[str, Path]:
    inputs = manifest.get("inputs", {})
    outputs = manifest.get("outputs", {})
    paths = {
        "candidate_pool": resolve_path(str(inputs["candidate_pool"]), base_dir),
        "k_table": resolve_path(str(inputs["k_table"]), base_dir),
        "source_result": resolve_path(str(inputs["source_result"]), base_dir),
        "assortment_result": resolve_path(manifest_output_path(outputs["assortment_result"]), base_dir),
    }
    missing = [name for name, path in paths.items() if not path.exists()]
    add_check(
        checks,
        "required_files_exist",
        not missing,
        "all required assortment files exist" if not missing else f"missing files: {missing}",
        {"checked_files": len(paths), "missing_files": len(missing)},
    )
    return paths


def load_candidate_context(path: Path) -> tuple[dict[tuple[str, str], dict[str, str]], dict[str, int]]:
    candidates: dict[tuple[str, str], dict[str, str]] = {}
    candidate_count_by_fdc: dict[str, int] = defaultdict(int)
    for row in iter_csv_rows(path):
        if not as_bool(row.get("candidate_flag", "false")):
            continue
        key = (row["fdc_id"], row["sku_id"])
        candidates[key] = row
        candidate_count_by_fdc[row["fdc_id"]] += 1
    return candidates, dict(candidate_count_by_fdc)


def load_k_table(path: Path) -> dict[str, dict[str, str]]:
    return {row["fdc_id"]: row for row in iter_csv_rows(path)}


def validate_result_header(path: Path, checks: list[dict[str, Any]]) -> None:
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
    missing = sorted(set(ASSORTMENT_RESULT_FIELDS) - set(fieldnames))
    extra = [field for field in fieldnames if field not in ASSORTMENT_RESULT_FIELDS]
    add_check(
        checks,
        "assortment_result_header",
        not missing and not extra,
        "assortment_result header matches schema"
        if not missing and not extra
        else f"missing={missing}, extra={extra}",
        {"field_count": len(fieldnames)},
    )


def validate_row_counts(manifest: dict[str, Any], path: Path, checks: list[dict[str, Any]]) -> None:
    actual = count_csv_rows(path)
    expected = int(manifest.get("row_counts", {}).get("assortment_result", -1))
    add_check(
        checks,
        "row_counts_match_manifest",
        actual == expected,
        "assortment_result row count matches manifest"
        if actual == expected
        else f"expected {expected}, got {actual}",
        {"expected": expected, "actual": actual},
    )


def validate_result_rows(
    manifest: dict[str, Any],
    result_path: Path,
    candidates: dict[tuple[str, str], dict[str, str]],
    k_by_fdc: dict[str, dict[str, str]],
    checks: list[dict[str, Any]],
) -> dict[str, Any]:
    expected = {
        "experiment_id": str(manifest["experiment_id"]),
        "data_version": str(manifest["data_version"]),
        "candidate_pool_version": str(manifest["candidate_pool_version"]),
        "k_rule_version": str(manifest["k_rule_version"]),
        "method_version": str(manifest["method_version"]),
        "assortment_version": str(manifest["assortment_version"]),
        "anchor_date": as_date_str(manifest["anchor_date"]),
        "effective_start_date": as_date_str(manifest["effective_start_date"]),
        "effective_end_date": as_date_str(manifest["effective_end_date"]),
    }
    errors: list[str] = []
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    row_count = 0
    for index, row in enumerate(iter_csv_rows(result_path), start=1):
        row_count += 1
        for field, value in expected.items():
            if row[field] != value:
                errors.append(f"row {index}: {field} mismatch")
                break
        key = (row["fdc_id"], row["sku_id"])
        candidate = candidates.get(key)
        if candidate is None:
            errors.append(f"row {index}: SKU-FDC pair not in candidate_pool")
        else:
            if not as_bool(candidate.get("eligible_flag", "false")):
                errors.append(f"row {index}: candidate is not eligible")
            if not as_bool(candidate.get("is_regular_product", "false")):
                errors.append(f"row {index}: candidate is not regular product")
        if row["source_tag"] not in ALLOWED_SOURCE_TAGS:
            errors.append(f"row {index}: invalid source_tag={row['source_tag']}")
        if row["fdc_id"] not in k_by_fdc:
            errors.append(f"row {index}: fdc_id missing from k_table")
        else:
            k_row = k_by_fdc[row["fdc_id"]]
            if as_int(row["selected_k"]) != as_int(k_row["selected_k"]):
                errors.append(f"row {index}: selected_k mismatch")
            if as_int(row["candidate_sku_count"]) != as_int(k_row["candidate_sku_count"]):
                errors.append(f"row {index}: candidate_sku_count mismatch")
        if as_int(row["rank"]) <= 0:
            errors.append(f"row {index}: rank must be positive")
        if not as_bool(row["selected_flag"]):
            errors.append(f"row {index}: published result must contain selected rows only")
        grouped[row["fdc_id"]].append(row)
        if len(errors) >= 30:
            break

    add_check(
        checks,
        "assortment_result_rows_valid",
        not errors,
        "all assortment_result rows satisfy version, candidate and field constraints"
        if not errors
        else "; ".join(errors[:10]),
        {"rows": row_count, "error_count": len(errors)},
    )
    return {"row_errors": len(errors), "rows": row_count, "grouped": grouped}


def validate_group_constraints(
    grouped: dict[str, list[dict[str, str]]],
    k_by_fdc: dict[str, dict[str, str]],
    checks: list[dict[str, Any]],
) -> dict[str, Any]:
    errors: list[str] = []
    fdc_count = 0
    total_selected = 0
    for fdc_id, rows in sorted(grouped.items()):
        fdc_count += 1
        total_selected += len(rows)
        selected_k = as_int(k_by_fdc.get(fdc_id, {}).get("selected_k"))
        sku_ids = [row["sku_id"] for row in rows]
        ranks = sorted(as_int(row["rank"]) for row in rows)
        if len(rows) > selected_k:
            errors.append(f"{fdc_id}: selected rows exceed selected_k")
        if len(sku_ids) != len(set(sku_ids)):
            errors.append(f"{fdc_id}: duplicate sku_id")
        if ranks != list(range(1, len(rows) + 1)):
            errors.append(f"{fdc_id}: rank is not continuous")
        if any(rank > selected_k for rank in ranks):
            errors.append(f"{fdc_id}: rank exceeds selected_k")
    add_check(
        checks,
        "fdc_group_constraints",
        not errors,
        "each FDC has unique SKU rows and continuous rank within K"
        if not errors
        else "; ".join(errors[:10]),
        {"fdc_count": fdc_count, "total_selected_rows": total_selected, "error_count": len(errors)},
    )
    return {"fdc_count": fdc_count, "total_selected_rows": total_selected, "group_errors": len(errors)}


def write_validation_report(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        f"# Assortment Validation Report: {summary['experiment_id']}",
        "",
        f"- checked_at: {summary['checked_at']}",
        f"- result: {'PASS' if summary['passed'] else 'FAIL'}",
        f"- manifest_path: {summary['manifest_path']}",
        "",
        "## Checks",
        "",
    ]
    for check in summary["checks"]:
        lines.extend(
            [
                f"### {check['name']}",
                "",
                f"- status: {'PASS' if check['passed'] else 'FAIL'}",
                f"- detail: {check['detail']}",
                "",
                "```json",
                json.dumps(check.get("metrics", {}), ensure_ascii=False, indent=2),
                "```",
                "",
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def validate_assortment_run(
    manifest_path: Path,
    write_outputs: bool = True,
    update_manifest: bool = True,
) -> dict[str, Any]:
    manifest = read_yaml(manifest_path)
    base_dir = Path.cwd()
    checks: list[dict[str, Any]] = []

    validate_date_window(manifest, checks)
    paths = validate_required_files(manifest, base_dir, checks)
    if all(path.exists() for path in paths.values()):
        validate_result_header(paths["assortment_result"], checks)
        validate_row_counts(manifest, paths["assortment_result"], checks)
        candidates, _candidate_count_by_fdc = load_candidate_context(paths["candidate_pool"])
        k_by_fdc = load_k_table(paths["k_table"])
        row_metrics = validate_result_rows(manifest, paths["assortment_result"], candidates, k_by_fdc, checks)
        group_metrics = validate_group_constraints(row_metrics["grouped"], k_by_fdc, checks)
    else:
        row_metrics = {"rows": 0, "row_errors": 0}
        group_metrics = {"fdc_count": 0, "total_selected_rows": 0, "group_errors": 0}

    passed = all(check["passed"] for check in checks)
    summary = {
        "experiment_id": manifest["experiment_id"],
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "manifest_path": str(manifest_path),
        "passed": passed,
        "checks": checks,
        "metrics": {
            "assortment_result_rows": row_metrics["rows"],
            "row_errors": row_metrics["row_errors"],
            "fdc_count": group_metrics["fdc_count"],
            "total_selected_rows": group_metrics["total_selected_rows"],
            "group_errors": group_metrics["group_errors"],
        },
    }

    if write_outputs:
        outputs = manifest["outputs"]
        validation_summary_output = Path(manifest_output_path(outputs["validation_summary"]))
        validation_report_output = Path(manifest_output_path(outputs["validation_report"]))
        validation_summary_path = resolve_path(str(validation_summary_output), base_dir)
        validation_report_path = resolve_path(str(validation_report_output), base_dir)
        write_json(validation_summary_path, summary)
        write_validation_report(validation_report_path, summary)
        if update_manifest:
            manifest["validation"] = {
                "passed": passed,
                "checked_at": summary["checked_at"],
                "validation_summary": str(validation_summary_output),
                "validation_report": str(validation_report_output),
            }
            manifest["outputs"]["validation_summary"] = file_entry(validation_summary_output)
            manifest["outputs"]["validation_report"] = file_entry(validation_report_output)
            write_yaml(manifest_path, manifest)
            summary["manifest_updated"] = True
    return summary
