"""Demand forecasting baselines for inventory allocation."""

from __future__ import annotations

import math
from collections import defaultdict
from pathlib import Path
from typing import Any

from inventory.src.common import (
    add_days,
    date_range,
    float_value,
    input_path,
    iter_csv_rows,
    parse_date,
    window_start,
    write_csv,
)


DEMAND_FORECAST_FIELDS = [
    "experiment_id",
    "data_version",
    "assortment_version",
    "inventory_version",
    "simulation_rule_version",
    "forecast_method",
    "forecast_version",
    "model_version",
    "decision_date",
    "forecast_date",
    "horizon_day",
    "node_id",
    "node_type",
    "rdc_id",
    "fdc_id",
    "sku_id",
    "forecast_qty",
    "base_forecast_qty",
    "historical_mean_qty",
    "historical_std_qty",
    "promotion_factor",
    "calendar_factor",
    "feature_window_start_date",
    "feature_window_end_date",
    "leakage_safe_flag",
]


def load_demand_history(path: Path, pairs: set[tuple[str, str]], start_date: str, end_date: str) -> dict[tuple[str, str], dict[str, int]]:
    history: dict[tuple[str, str], dict[str, int]] = {pair: {} for pair in pairs}
    start = parse_date(start_date)
    end = parse_date(end_date)
    for row in iter_csv_rows(path):
        key = (row["fdc_id"], row["sku_id"])
        if key not in pairs:
            continue
        row_date = parse_date(row["date"])
        if start <= row_date <= end:
            history.setdefault(key, {})[row["date"]] = int(row["demand_qty"])
    return history


def load_calendar_factors(path: Path, enabled: bool) -> dict[str, float]:
    if not enabled:
        return {}
    factors: dict[str, float] = {}
    for row in iter_csv_rows(path):
        factors[row["date"]] = float_value(row.get("demand_multiplier"), 1.0)
    return factors


def load_promotion_factors(path: Path, enabled: bool) -> dict[tuple[str, str], float]:
    if not enabled:
        return {}
    factors: dict[tuple[str, str], float] = {}
    for row in iter_csv_rows(path):
        factors[(row["date"], row["sku_id"])] = max(factors.get((row["date"], row["sku_id"]), 1.0), float_value(row.get("planned_demand_lift"), 1.0))
    return factors


def build_demand_forecast_rows(config: dict[str, Any], inventory_state_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    forecast_cfg = config["forecast"]
    decision_date = str(config["decision_date"])
    history_window_days = int(forecast_cfg.get("history_window_days", 28))
    feature_start = window_start(decision_date, history_window_days)
    feature_end = decision_date
    effective_start = str(config["effective_start_date"])
    horizon_days = int(forecast_cfg.get("horizon_days", 7))
    effective_end = min(parse_date(str(config["effective_end_date"])), parse_date(add_days(effective_start, horizon_days - 1)))
    forecast_dates = date_range(effective_start, effective_end.strftime("%Y-%m-%d"))

    fdc_rows = [row for row in inventory_state_rows if row["node_type"] == "FDC"]
    pairs = {(str(row["fdc_id"]), str(row["sku_id"])) for row in fdc_rows}
    demand_history = load_demand_history(input_path(config, "fdc_sku_daily_demand"), pairs, feature_start, feature_end)
    calendar_factors = load_calendar_factors(input_path(config, "calendar"), bool(forecast_cfg.get("calendar_adjustment_enabled", True)))
    promotion_factors = load_promotion_factors(input_path(config, "promotion_plan"), bool(forecast_cfg.get("promotion_adjustment_enabled", True)))

    rows: list[dict[str, Any]] = []
    for state_row in sorted(fdc_rows, key=lambda row: (row["fdc_id"], row["sku_id"])):
        fdc_id = str(state_row["fdc_id"])
        sku_id = str(state_row["sku_id"])
        history_values = [demand_history.get((fdc_id, sku_id), {}).get(date, 0) for date in date_range(feature_start, feature_end)]
        hist_mean = sum(history_values) / len(history_values) if history_values else float(forecast_cfg.get("fallback_daily_demand", 0.0))
        hist_std = math.sqrt(sum((value - hist_mean) ** 2 for value in history_values) / len(history_values)) if history_values else 0.0

        for index, forecast_date in enumerate(forecast_dates, start=1):
            promotion_factor = promotion_factors.get((forecast_date, sku_id), 1.0)
            calendar_factor = calendar_factors.get(forecast_date, 1.0)
            base_forecast = hist_mean
            forecast_qty = max(0.0, base_forecast * promotion_factor * calendar_factor)
            rows.append(
                forecast_row(
                    config=config,
                    forecast_method=str(forecast_cfg.get("method", "historical_mean")),
                    forecast_version=str(forecast_cfg.get("forecast_version", "historical_mean_forecast_v001")),
                    model_version=str(forecast_cfg.get("model_version", "none")),
                    decision_date=decision_date,
                    forecast_date=forecast_date,
                    horizon_day=index,
                    node_id=fdc_id,
                    node_type="FDC",
                    rdc_id=str(state_row["rdc_id"]),
                    fdc_id=fdc_id,
                    sku_id=sku_id,
                    forecast_qty=forecast_qty,
                    base_forecast_qty=base_forecast,
                    historical_mean_qty=hist_mean,
                    historical_std_qty=hist_std,
                    promotion_factor=promotion_factor,
                    calendar_factor=calendar_factor,
                    feature_window_start_date=feature_start,
                    feature_window_end_date=feature_end,
                )
            )

    rows.extend(build_rdc_forecast_rows(config, rows))
    return rows


def build_rdc_forecast_rows(config: dict[str, Any], fdc_forecast_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in fdc_forecast_rows:
        grouped[(str(row["forecast_date"]), str(row["rdc_id"]), str(row["sku_id"]))].append(row)

    rdc_rows = []
    for (forecast_date, rdc_id, sku_id), rows in sorted(grouped.items()):
        first = rows[0]
        rdc_rows.append(
            forecast_row(
                config=config,
                forecast_method=str(first["forecast_method"]),
                forecast_version=str(first["forecast_version"]),
                model_version=str(first["model_version"]),
                decision_date=str(first["decision_date"]),
                forecast_date=forecast_date,
                horizon_day=int(first["horizon_day"]),
                node_id=rdc_id,
                node_type="RDC",
                rdc_id=rdc_id,
                fdc_id="",
                sku_id=sku_id,
                forecast_qty=sum(float_value(row["forecast_qty"]) for row in rows),
                base_forecast_qty=sum(float_value(row["base_forecast_qty"]) for row in rows),
                historical_mean_qty=sum(float_value(row["historical_mean_qty"]) for row in rows),
                historical_std_qty=sum(float_value(row["historical_std_qty"]) for row in rows),
                promotion_factor=1.0,
                calendar_factor=float_value(first["calendar_factor"], 1.0),
                feature_window_start_date=str(first["feature_window_start_date"]),
                feature_window_end_date=str(first["feature_window_end_date"]),
            )
        )
    return rdc_rows


def forecast_row(
    config: dict[str, Any],
    forecast_method: str,
    forecast_version: str,
    model_version: str,
    decision_date: str,
    forecast_date: str,
    horizon_day: int,
    node_id: str,
    node_type: str,
    rdc_id: str,
    fdc_id: str,
    sku_id: str,
    forecast_qty: float,
    base_forecast_qty: float,
    historical_mean_qty: float,
    historical_std_qty: float,
    promotion_factor: float,
    calendar_factor: float,
    feature_window_start_date: str,
    feature_window_end_date: str,
) -> dict[str, Any]:
    return {
        "experiment_id": config["experiment_id"],
        "data_version": config["data_version"],
        "assortment_version": config["assortment_version"],
        "inventory_version": config["inventory_version"],
        "simulation_rule_version": config["simulation_rule_version"],
        "forecast_method": forecast_method,
        "forecast_version": forecast_version,
        "model_version": model_version,
        "decision_date": decision_date,
        "forecast_date": forecast_date,
        "horizon_day": horizon_day,
        "node_id": node_id,
        "node_type": node_type,
        "rdc_id": rdc_id,
        "fdc_id": fdc_id,
        "sku_id": sku_id,
        "forecast_qty": round(forecast_qty, 6),
        "base_forecast_qty": round(base_forecast_qty, 6),
        "historical_mean_qty": round(historical_mean_qty, 6),
        "historical_std_qty": round(historical_std_qty, 6),
        "promotion_factor": round(promotion_factor, 6),
        "calendar_factor": round(calendar_factor, 6),
        "feature_window_start_date": feature_window_start_date,
        "feature_window_end_date": feature_window_end_date,
        "leakage_safe_flag": "true",
    }


def write_demand_forecast(config: dict[str, Any], rows: list[dict[str, Any]]) -> tuple[Path, int]:
    run_dir = Path(str(config["output"]["run_dir"]))
    output_path = run_dir / "demand_forecast.csv"
    count = write_csv(output_path, DEMAND_FORECAST_FIELDS, rows)
    return output_path, count
