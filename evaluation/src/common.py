"""Shared helpers for FAIA evaluation runs."""

from __future__ import annotations

import csv
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml


def infer_repo_root(config_path: Path) -> Path:
    resolved = config_path.resolve()
    for parent in [resolved.parent, *resolved.parents]:
        if (parent / "evaluation").exists() and (parent / "doc").exists():
            return parent
    return Path.cwd()


def resolve_path(path: str | Path, repo_root: Path) -> Path:
    candidate = Path(str(path))
    if candidate.is_absolute():
        return candidate
    return repo_root / candidate


def relative_path(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, sort_keys=False, allow_unicode=True)


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: csv_value(row.get(name)) for name in fieldnames})


def csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def nested_get(payload: dict[str, Any], path: str, default: Any = None) -> Any:
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def output_path(entry: Any) -> str:
    if isinstance(entry, dict):
        return to_text(entry.get("path"))
    return to_text(entry)


def file_entry(path: Path, repo_root: Path, rows: int | None = None) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "path": relative_path(path, repo_root),
        "bytes": path.stat().st_size if path.exists() else 0,
    }
    if rows is not None:
        entry["rows"] = rows
    return entry


def row_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        next(reader, None)
        return sum(1 for _ in reader)


def numeric_items(payload: dict[str, Any]) -> list[tuple[str, int | float]]:
    items: list[tuple[str, int | float]] = []
    for key, value in payload.items():
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            items.append((key, value))
    return items


def validation_status(manifest: dict[str, Any]) -> str:
    validation = manifest.get("validation", {})
    if not validation:
        return "unknown"
    if "status" in validation:
        return to_text(validation["status"])
    if "passed" in validation:
        return "PASS" if bool(validation["passed"]) else "FAIL"
    return "unknown"
