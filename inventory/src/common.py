"""Shared utilities for FAIA inventory allocation."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Iterator

import yaml


BOOL_TRUE = {"true", "1", "yes", "y", "t"}


def parse_date(value: str) -> datetime:
    return datetime.strptime(str(value), "%Y-%m-%d")


def date_text(value: datetime) -> str:
    return value.strftime("%Y-%m-%d")


def add_days(value: str, days: int) -> str:
    return date_text(parse_date(value) + timedelta(days=days))


def date_range(start_date: str, end_date: str) -> list[str]:
    start = parse_date(start_date)
    end = parse_date(end_date)
    if end < start:
        raise ValueError(f"end_date {end_date} is earlier than start_date {start_date}")
    days = []
    current = start
    while current <= end:
        days.append(date_text(current))
        current += timedelta(days=1)
    return days


def window_start(end_date: str, window_days: int) -> str:
    if window_days <= 0:
        raise ValueError("window_days must be positive")
    return add_days(end_date, -(window_days - 1))


def read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        payload = yaml.safe_load(f)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return payload


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, sort_keys=False, allow_unicode=True)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in BOOL_TRUE


def bool_text(value: bool) -> str:
    return "true" if value else "false"


def int_value(value: object, default: int = 0) -> int:
    if value is None or value == "":
        return default
    return int(float(str(value)))


def float_value(value: object, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    return float(str(value))


def is_lfs_pointer(path: Path) -> bool:
    if not path.exists() or path.stat().st_size > 512:
        return False
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        first_line = f.readline().strip()
    return first_line == "version https://git-lfs.github.com/spec/v1"


def iter_csv_rows(path: Path) -> Iterator[dict[str, str]]:
    if is_lfs_pointer(path):
        raise ValueError(f"{path} is a Git LFS pointer; materialize the CSV before running inventory allocation")
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError(f"{path} has no CSV header")
        yield from reader


def write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
            count += 1
    return count


def count_csv_rows(path: Path) -> int:
    with path.open("r", encoding="utf-8", newline="") as f:
        return sum(1 for _ in csv.DictReader(f))


def file_entry(path: Path, rows: int | None = None) -> dict[str, Any]:
    entry: dict[str, Any] = {"path": str(path), "bytes": path.stat().st_size if path.exists() else 0}
    if rows is not None:
        entry["rows"] = rows
    return entry


def config_path(config: dict[str, Any], section: str, name: str) -> Path:
    return Path(str(config[section][name]))


def input_path(config: dict[str, Any], name: str) -> Path:
    return config_path(config, "inputs", name)
