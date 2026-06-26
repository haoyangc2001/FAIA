#!/usr/bin/env python3
"""Validate FAIA stage-1 data artifacts."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


def read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def parse_date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d")


def int_value(value: str) -> int:
    return int(float(value))


def float_value(value: str) -> float:
    return float(value)


def status_text(passed: bool, severity: str) -> str:
    if passed:
        return "PASS"
    return "WARN" if severity == "warning" else "FAIL"


class Validator:
    def __init__(self, data_version: str) -> None:
        self.data_version = data_version
        self.checks: list[dict[str, Any]] = []
        self.counts: dict[str, dict[str, int]] = {
            "synthetic": {},
            "processed": {},
            "features": {},
            "splits": {},
        }

    def check(self, area: str, name: str, passed: bool, details: str, severity: str = "error") -> None:
        self.checks.append(
            {
                "area": area,
                "name": name,
                "status": status_text(passed, severity),
                "details": details,
            }
        )

    @property
    def error_count(self) -> int:
        return sum(1 for item in self.checks if item["status"] == "FAIL")

    @property
    def warning_count(self) -> int:
        return sum(1 for item in self.checks if item["status"] == "WARN")

    @property
    def status(self) -> str:
        return "PASS" if self.error_count == 0 else "FAIL"


def csv_header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        return next(reader)


def line_count(path: Path, has_header: bool = True) -> int:
    total = sum(1 for _ in path.open("r", encoding="utf-8", newline=""))
    return total - 1 if has_header else total


def validate_files_and_headers(
    validator: Validator,
    synthetic_dir: Path,
    processed_dir: Path,
    features_ml_dir: Path,
    features_inventory_dir: Path,
    splits_dir: Path,
) -> None:
    expected_files = [
        synthetic_dir / "sku_master.csv",
        synthetic_dir / "warehouse_master.csv",
        synthetic_dir / "sku_fdc_eligibility.csv",
        synthetic_dir / "calendar.csv",
        synthetic_dir / "promotion_plan.csv",
        synthetic_dir / "orders.csv",
        synthetic_dir / "order_items.csv",
        synthetic_dir / "inventory_snapshot.csv",
        synthetic_dir / "transfer_plan.csv",
        synthetic_dir / "stockout_events.csv",
        synthetic_dir / "cost_config.csv",
        synthetic_dir / "manifest.yaml",
        processed_dir / "fdc_sku_daily_demand.csv",
        processed_dir / "order_type_table.csv",
        processed_dir / "order_type_items.csv",
        processed_dir / "inventory_daily_state.csv",
        processed_dir / "candidate_pool_base.csv",
        processed_dir / "manifest.yaml",
        features_ml_dir / "fdc_sku_features.csv",
        features_ml_dir / "manifest.yaml",
        features_inventory_dir / "inventory_features.csv",
        features_inventory_dir / "manifest.yaml",
        splits_dir / "train_dates.txt",
        splits_dir / "val_dates.txt",
        splits_dir / "test_dates.txt",
        splits_dir / "manifest.yaml",
    ]
    missing = [str(path) for path in expected_files if not path.exists()]
    validator.check("files", "required_artifacts_exist", not missing, f"missing={missing}" if missing else "all required files exist")

    schema_dir = Path("data/schemas")
    for schema_path in sorted(schema_dir.glob("*.schema.yaml")):
        schema = read_yaml(schema_path)
        table = schema["table"]
        path = synthetic_dir / f"{table}.csv"
        if not path.exists():
            continue
        expected = [field["name"] for field in schema["fields"]]
        actual = csv_header(path)
        validator.check(
            "schema",
            f"{table}_header_matches_schema",
            actual == expected,
            f"expected={expected}, actual={actual}",
        )

    expected_headers = {
        processed_dir / "fdc_sku_daily_demand.csv": ["date", "fdc_id", "sku_id", "order_count", "demand_qty"],
        processed_dir / "order_type_table.csv": [
            "order_type_id",
            "fdc_id",
            "order_type_key",
            "sku_count",
            "order_count",
            "total_qty",
            "first_order_date",
            "last_order_date",
        ],
        processed_dir / "order_type_items.csv": ["order_type_id", "fdc_id", "sku_id", "item_rank"],
        processed_dir / "inventory_daily_state.csv": [
            "date",
            "node_id",
            "node_type",
            "sku_id",
            "on_hand_qty",
            "reserved_qty",
            "in_transit_qty",
            "available_qty",
            "inventory_position_qty",
        ],
        processed_dir / "candidate_pool_base.csv": [
            "fdc_id",
            "sku_id",
            "rdc_id",
            "eligible_flag",
            "category_id",
            "brand_id",
            "temperature_zone",
            "price",
            "volume",
            "weight",
            "shelf_life_days",
            "is_regular_product",
            "base_popularity",
            "total_demand_qty",
            "demand_order_count",
            "active_demand_days",
        ],
        features_ml_dir / "fdc_sku_features.csv": [
            "anchor_date",
            "fdc_id",
            "sku_id",
            "category_id",
            "brand_id",
            "temperature_zone",
            "base_popularity",
            "price",
            "is_regular_product",
            "hist_7d_qty",
            "hist_7d_orders",
            "hist_14d_qty",
            "hist_14d_orders",
            "hist_30d_qty",
            "hist_30d_orders",
            "hist_30d_active_days",
            "hist_60d_qty",
            "hist_60d_orders",
            "future_promo_days_14d",
            "future_campaign_days_14d",
        ],
        features_inventory_dir / "inventory_features.csv": [
            "anchor_date",
            "fdc_id",
            "sku_id",
            "on_hand_qty",
            "reserved_qty",
            "in_transit_qty",
            "available_qty",
            "inventory_position_qty",
            "hist_7d_qty",
            "hist_7d_orders",
            "hist_14d_qty",
            "hist_14d_orders",
            "hist_30d_qty",
            "hist_30d_orders",
            "hist_30d_active_days",
            "future_promo_days_14d",
            "lead_time_min_days",
            "lead_time_max_days",
        ],
    }
    for path, expected in expected_headers.items():
        if not path.exists():
            continue
        actual = csv_header(path)
        validator.check("schema", f"{path.name}_header_matches_contract", actual == expected, f"expected={expected}, actual={actual}")


def load_static_tables(
    validator: Validator,
    synthetic_dir: Path,
) -> tuple[set[str], dict[str, dict[str, str]], set[str], set[str], dict[str, str], list[str], set[tuple[str, str]]]:
    sku_ids: set[str] = set()
    duplicate_skus = 0
    sku_numeric_errors = 0
    with (synthetic_dir / "sku_master.csv").open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            validator.counts["synthetic"]["sku_master"] = validator.counts["synthetic"].get("sku_master", 0) + 1
            if row["sku_id"] in sku_ids:
                duplicate_skus += 1
            sku_ids.add(row["sku_id"])
            try:
                if float_value(row["price"]) < 0 or float_value(row["volume"]) <= 0 or float_value(row["weight"]) <= 0:
                    sku_numeric_errors += 1
                if int_value(row["shelf_life_days"]) <= 0 or float_value(row["base_popularity"]) < 0:
                    sku_numeric_errors += 1
            except ValueError:
                sku_numeric_errors += 1
    validator.check("primary_key", "sku_master_sku_id_unique", duplicate_skus == 0, f"duplicate_skus={duplicate_skus}")
    validator.check("business_rule", "sku_master_numeric_fields_valid", sku_numeric_errors == 0, f"numeric_errors={sku_numeric_errors}")

    warehouse_by_id: dict[str, dict[str, str]] = {}
    duplicate_nodes = 0
    rdc_ids: set[str] = set()
    fdc_ids: set[str] = set()
    fdc_to_rdc: dict[str, str] = {}
    warehouse_errors = 0
    with (synthetic_dir / "warehouse_master.csv").open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        validator.counts["synthetic"]["warehouse_master"] = validator.counts["synthetic"].get("warehouse_master", 0) + 1
        node_id = row["node_id"]
        if node_id in warehouse_by_id:
            duplicate_nodes += 1
        warehouse_by_id[node_id] = row
        if row["node_type"] == "RDC":
            rdc_ids.add(node_id)
        elif row["node_type"] == "FDC":
            fdc_ids.add(node_id)
            fdc_to_rdc[node_id] = row["rdc_id"]
        else:
            warehouse_errors += 1
        if int_value(row["capacity_units"]) <= 0:
            warehouse_errors += 1
    for fdc_id, rdc_id in fdc_to_rdc.items():
        if rdc_id not in rdc_ids:
            warehouse_errors += 1
    validator.check("primary_key", "warehouse_master_node_id_unique", duplicate_nodes == 0, f"duplicate_nodes={duplicate_nodes}")
    validator.check("foreign_key", "fdc_rdc_relationship_valid", warehouse_errors == 0, f"relationship_or_capacity_errors={warehouse_errors}")

    calendar_dates: list[str] = []
    calendar_set: set[str] = set()
    duplicate_dates = 0
    calendar_errors = 0
    with (synthetic_dir / "calendar.csv").open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            validator.counts["synthetic"]["calendar"] = validator.counts["synthetic"].get("calendar", 0) + 1
            date_value = row["date"]
            if date_value in calendar_set:
                duplicate_dates += 1
            calendar_set.add(date_value)
            calendar_dates.append(date_value)
            try:
                if int_value(row["day_of_week"]) < 1 or int_value(row["day_of_week"]) > 7:
                    calendar_errors += 1
                if float_value(row["demand_multiplier"]) <= 0:
                    calendar_errors += 1
            except ValueError:
                calendar_errors += 1
    sorted_dates = sorted(calendar_dates, key=parse_date)
    validator.check("primary_key", "calendar_date_unique", duplicate_dates == 0, f"duplicate_dates={duplicate_dates}")
    validator.check("business_rule", "calendar_dates_sorted", calendar_dates == sorted_dates, "calendar is chronological")
    validator.check("business_rule", "calendar_fields_valid", calendar_errors == 0, f"calendar_errors={calendar_errors}")

    eligible_pairs: set[tuple[str, str]] = set()
    all_eligibility_pairs: set[tuple[str, str]] = set()
    eligibility_errors = 0
    duplicate_eligibility = 0
    with (synthetic_dir / "sku_fdc_eligibility.csv").open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            validator.counts["synthetic"]["sku_fdc_eligibility"] = validator.counts["synthetic"].get("sku_fdc_eligibility", 0) + 1
            key = (row["sku_id"], row["fdc_id"])
            if key in all_eligibility_pairs:
                duplicate_eligibility += 1
            all_eligibility_pairs.add(key)
            if row["sku_id"] not in sku_ids or row["fdc_id"] not in fdc_ids:
                eligibility_errors += 1
            if row["rdc_id"] != fdc_to_rdc.get(row["fdc_id"]):
                eligibility_errors += 1
            if row["eligible_flag"] == "true":
                eligible_pairs.add(key)
                if row["ineligible_reason"]:
                    eligibility_errors += 1
            elif row["eligible_flag"] == "false":
                if not row["ineligible_reason"]:
                    eligibility_errors += 1
            else:
                eligibility_errors += 1
    validator.check("primary_key", "sku_fdc_eligibility_pair_unique", duplicate_eligibility == 0, f"duplicate_pairs={duplicate_eligibility}")
    validator.check("foreign_key", "sku_fdc_eligibility_references_valid", eligibility_errors == 0, f"errors={eligibility_errors}")

    return sku_ids, warehouse_by_id, rdc_ids, fdc_ids, fdc_to_rdc, calendar_dates, eligible_pairs


def validate_promotions_and_costs(
    validator: Validator,
    synthetic_dir: Path,
    sku_ids: set[str],
    calendar_dates: list[str],
) -> None:
    calendar_set = set(calendar_dates)
    duplicate_promotions = 0
    promotion_errors = 0
    promotion_keys: set[tuple[str, str]] = set()
    with (synthetic_dir / "promotion_plan.csv").open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            validator.counts["synthetic"]["promotion_plan"] = validator.counts["synthetic"].get("promotion_plan", 0) + 1
            key = (row["date"], row["sku_id"])
            if key in promotion_keys:
                duplicate_promotions += 1
            promotion_keys.add(key)
            if row["date"] not in calendar_set or row["sku_id"] not in sku_ids:
                promotion_errors += 1
            try:
                if float_value(row["discount_rate"]) < 0 or float_value(row["coupon_value"]) < 0:
                    promotion_errors += 1
                if int_value(row["planned_exposure_level"]) < 0 or float_value(row["planned_demand_lift"]) < 1:
                    promotion_errors += 1
            except ValueError:
                promotion_errors += 1
    validator.check("primary_key", "promotion_plan_date_sku_unique", duplicate_promotions == 0, f"duplicate_promotions={duplicate_promotions}")
    validator.check("foreign_key", "promotion_plan_references_valid", promotion_errors == 0, f"errors={promotion_errors}")

    cost_items = set()
    cost_errors = 0
    with (synthetic_dir / "cost_config.csv").open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            validator.counts["synthetic"]["cost_config"] = validator.counts["synthetic"].get("cost_config", 0) + 1
            cost_items.add(row["cost_item"])
            try:
                if float_value(row["value"]) < 0:
                    cost_errors += 1
            except ValueError:
                cost_errors += 1
    expected_items = {"transfer_cost", "rdc_fallback_cost", "lost_sales_cost", "holding_cost"}
    validator.check("business_rule", "cost_config_items_complete", cost_items == expected_items, f"cost_items={sorted(cost_items)}")
    validator.check("business_rule", "cost_config_values_non_negative", cost_errors == 0, f"errors={cost_errors}")


def validate_orders(
    validator: Validator,
    synthetic_dir: Path,
    sku_ids: set[str],
    rdc_ids: set[str],
    fdc_ids: set[str],
    fdc_to_rdc: dict[str, str],
    calendar_dates: list[str],
) -> None:
    calendar_set = set(calendar_dates)
    order_remaining_items: dict[str, int] = {}
    duplicate_orders = 0
    order_errors = 0
    with (synthetic_dir / "orders.csv").open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            validator.counts["synthetic"]["orders"] = validator.counts["synthetic"].get("orders", 0) + 1
            order_id = row["order_id"]
            if order_id in order_remaining_items:
                duplicate_orders += 1
            try:
                item_count = int_value(row["order_item_count"])
            except ValueError:
                item_count = -1
            order_remaining_items[order_id] = item_count
            if item_count < 1:
                order_errors += 1
            if row["order_date"] not in calendar_set or row["rdc_id"] not in rdc_ids or row["fdc_id"] not in fdc_ids:
                order_errors += 1
            if row["rdc_id"] != fdc_to_rdc.get(row["fdc_id"]):
                order_errors += 1
    validator.check("primary_key", "orders_order_id_unique", duplicate_orders == 0, f"duplicate_orders={duplicate_orders}")
    validator.check("foreign_key", "orders_references_valid", order_errors == 0, f"errors={order_errors}")

    item_errors = 0
    unknown_order_items = 0
    for order_id in list(order_remaining_items):
        if order_remaining_items[order_id] < 0:
            item_errors += 1
    with (synthetic_dir / "order_items.csv").open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            validator.counts["synthetic"]["order_items"] = validator.counts["synthetic"].get("order_items", 0) + 1
            order_id = row["order_id"]
            if order_id not in order_remaining_items:
                unknown_order_items += 1
            else:
                order_remaining_items[order_id] -= 1
            if row["sku_id"] not in sku_ids:
                item_errors += 1
            try:
                if int_value(row["qty"]) <= 0 or float_value(row["unit_price"]) < 0:
                    item_errors += 1
            except ValueError:
                item_errors += 1
    unmatched_orders = sum(1 for remaining in order_remaining_items.values() if remaining != 0)
    validator.check("foreign_key", "order_items_references_orders_and_skus", unknown_order_items == 0 and item_errors == 0, f"unknown_order_items={unknown_order_items}, item_errors={item_errors}")
    validator.check("business_rule", "orders_item_count_matches_order_items", unmatched_orders == 0, f"unmatched_orders={unmatched_orders}")


def validate_inventory_transfer_stockout(
    validator: Validator,
    synthetic_dir: Path,
    sku_ids: set[str],
    warehouse_by_id: dict[str, dict[str, str]],
    rdc_ids: set[str],
    fdc_ids: set[str],
    fdc_to_rdc: dict[str, str],
    calendar_dates: list[str],
) -> None:
    calendar_set = set(calendar_dates)
    inventory_errors = 0
    with (synthetic_dir / "inventory_snapshot.csv").open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            validator.counts["synthetic"]["inventory_snapshot"] = validator.counts["synthetic"].get("inventory_snapshot", 0) + 1
            if row["date"] not in calendar_set or row["node_id"] not in warehouse_by_id or row["sku_id"] not in sku_ids:
                inventory_errors += 1
            if row["node_type"] != warehouse_by_id.get(row["node_id"], {}).get("node_type"):
                inventory_errors += 1
            try:
                if int_value(row["on_hand_qty"]) < 0 or int_value(row["reserved_qty"]) < 0 or int_value(row["in_transit_qty"]) < 0:
                    inventory_errors += 1
            except ValueError:
                inventory_errors += 1
    validator.check("business_rule", "inventory_snapshot_references_and_quantities_valid", inventory_errors == 0, f"errors={inventory_errors}")

    transfer_errors = 0
    duplicate_transfers = 0
    transfer_ids: set[str] = set()
    with (synthetic_dir / "transfer_plan.csv").open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            validator.counts["synthetic"]["transfer_plan"] = validator.counts["synthetic"].get("transfer_plan", 0) + 1
            transfer_id = row["transfer_id"]
            if transfer_id in transfer_ids:
                duplicate_transfers += 1
            transfer_ids.add(transfer_id)
            if row["rdc_id"] not in rdc_ids or row["fdc_id"] not in fdc_ids or row["sku_id"] not in sku_ids:
                transfer_errors += 1
            if row["rdc_id"] != fdc_to_rdc.get(row["fdc_id"]):
                transfer_errors += 1
            try:
                if int_value(row["transfer_qty"]) <= 0 or int_value(row["lead_time_days"]) < 0:
                    transfer_errors += 1
                if parse_date(row["arrival_date"]) < parse_date(row["ship_date"]):
                    transfer_errors += 1
                if row["ship_date"] not in calendar_set:
                    transfer_errors += 1
            except ValueError:
                transfer_errors += 1
    validator.check("primary_key", "transfer_plan_transfer_id_unique", duplicate_transfers == 0, f"duplicate_transfers={duplicate_transfers}")
    validator.check("foreign_key", "transfer_plan_references_valid", transfer_errors == 0, f"errors={transfer_errors}")

    stockout_errors = 0
    allowed_reasons = {"not_assorted", "insufficient_fdc_inventory", "insufficient_rdc_inventory"}
    with (synthetic_dir / "stockout_events.csv").open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            validator.counts["synthetic"]["stockout_events"] = validator.counts["synthetic"].get("stockout_events", 0) + 1
            if row["date"] not in calendar_set or row["node_id"] not in warehouse_by_id or row["sku_id"] not in sku_ids:
                stockout_errors += 1
            if row["node_type"] != warehouse_by_id.get(row["node_id"], {}).get("node_type"):
                stockout_errors += 1
            if row["stockout_reason"] not in allowed_reasons:
                stockout_errors += 1
            try:
                if int_value(row["stockout_qty"]) < 0:
                    stockout_errors += 1
            except ValueError:
                stockout_errors += 1
    validator.check("business_rule", "stockout_events_references_and_quantities_valid", stockout_errors == 0, f"errors={stockout_errors}")


def validate_processed(
    validator: Validator,
    processed_dir: Path,
    sku_ids: set[str],
    warehouse_by_id: dict[str, dict[str, str]],
    fdc_ids: set[str],
    eligible_pairs: set[tuple[str, str]],
    calendar_dates: list[str],
) -> set[tuple[str, str]]:
    calendar_set = set(calendar_dates)
    daily_demand_errors = 0
    daily_demand_keys: set[tuple[str, str, str]] = set()
    duplicate_daily_demand = 0
    with (processed_dir / "fdc_sku_daily_demand.csv").open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            validator.counts["processed"]["fdc_sku_daily_demand"] = validator.counts["processed"].get("fdc_sku_daily_demand", 0) + 1
            key = (row["date"], row["fdc_id"], row["sku_id"])
            if key in daily_demand_keys:
                duplicate_daily_demand += 1
            daily_demand_keys.add(key)
            if row["date"] not in calendar_set or row["fdc_id"] not in fdc_ids or row["sku_id"] not in sku_ids:
                daily_demand_errors += 1
            try:
                if int_value(row["order_count"]) < 0 or int_value(row["demand_qty"]) < 0:
                    daily_demand_errors += 1
            except ValueError:
                daily_demand_errors += 1
    validator.check("primary_key", "fdc_sku_daily_demand_key_unique", duplicate_daily_demand == 0, f"duplicate_keys={duplicate_daily_demand}")
    validator.check("foreign_key", "fdc_sku_daily_demand_references_valid", daily_demand_errors == 0, f"errors={daily_demand_errors}")

    order_type_ids: set[str] = set()
    order_type_errors = 0
    duplicate_order_types = 0
    with (processed_dir / "order_type_table.csv").open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            validator.counts["processed"]["order_type_table"] = validator.counts["processed"].get("order_type_table", 0) + 1
            order_type_id = row["order_type_id"]
            if order_type_id in order_type_ids:
                duplicate_order_types += 1
            order_type_ids.add(order_type_id)
            sku_count = len(row["order_type_key"].split("|")) if row["order_type_key"] else 0
            if row["fdc_id"] not in fdc_ids or sku_count != int_value(row["sku_count"]):
                order_type_errors += 1
            if int_value(row["order_count"]) <= 0 or int_value(row["total_qty"]) <= 0:
                order_type_errors += 1
    validator.check("primary_key", "order_type_table_id_unique", duplicate_order_types == 0, f"duplicate_order_type_ids={duplicate_order_types}")
    validator.check("business_rule", "order_type_table_values_valid", order_type_errors == 0, f"errors={order_type_errors}")

    order_type_item_errors = 0
    with (processed_dir / "order_type_items.csv").open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            validator.counts["processed"]["order_type_items"] = validator.counts["processed"].get("order_type_items", 0) + 1
            if row["order_type_id"] not in order_type_ids or row["fdc_id"] not in fdc_ids or row["sku_id"] not in sku_ids:
                order_type_item_errors += 1
            try:
                if int_value(row["item_rank"]) < 1:
                    order_type_item_errors += 1
            except ValueError:
                order_type_item_errors += 1
    validator.check("foreign_key", "order_type_items_references_valid", order_type_item_errors == 0, f"errors={order_type_item_errors}")

    inventory_state_errors = 0
    with (processed_dir / "inventory_daily_state.csv").open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            validator.counts["processed"]["inventory_daily_state"] = validator.counts["processed"].get("inventory_daily_state", 0) + 1
            if row["date"] not in calendar_set or row["node_id"] not in warehouse_by_id or row["sku_id"] not in sku_ids:
                inventory_state_errors += 1
            try:
                on_hand = int_value(row["on_hand_qty"])
                reserved = int_value(row["reserved_qty"])
                in_transit = int_value(row["in_transit_qty"])
                available = int_value(row["available_qty"])
                position = int_value(row["inventory_position_qty"])
                if min(on_hand, reserved, in_transit, available, position) < 0:
                    inventory_state_errors += 1
                if available != max(0, on_hand - reserved) or position != available + in_transit:
                    inventory_state_errors += 1
            except ValueError:
                inventory_state_errors += 1
    validator.check("business_rule", "inventory_daily_state_derived_fields_valid", inventory_state_errors == 0, f"errors={inventory_state_errors}")

    candidate_errors = 0
    candidate_pairs: set[tuple[str, str]] = set()
    duplicate_candidates = 0
    with (processed_dir / "candidate_pool_base.csv").open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            validator.counts["processed"]["candidate_pool_base"] = validator.counts["processed"].get("candidate_pool_base", 0) + 1
            key = (row["sku_id"], row["fdc_id"])
            candidate_key = (row["fdc_id"], row["sku_id"])
            if candidate_key in candidate_pairs:
                duplicate_candidates += 1
            candidate_pairs.add(candidate_key)
            if key not in eligible_pairs or row["eligible_flag"] != "true":
                candidate_errors += 1
            try:
                if int_value(row["total_demand_qty"]) < 0 or int_value(row["demand_order_count"]) < 0 or int_value(row["active_demand_days"]) < 0:
                    candidate_errors += 1
            except ValueError:
                candidate_errors += 1
    validator.check("primary_key", "candidate_pool_base_pair_unique", duplicate_candidates == 0, f"duplicate_candidates={duplicate_candidates}")
    validator.check("foreign_key", "candidate_pool_base_subset_of_eligible_pairs", candidate_errors == 0, f"errors={candidate_errors}")
    return candidate_pairs


def validate_features_and_splits(
    validator: Validator,
    features_ml_dir: Path,
    features_inventory_dir: Path,
    splits_dir: Path,
    candidate_pairs: set[tuple[str, str]],
    calendar_dates: list[str],
) -> None:
    split_files = {
        "train": splits_dir / "train_dates.txt",
        "val": splits_dir / "val_dates.txt",
        "test": splits_dir / "test_dates.txt",
    }
    split_dates: dict[str, list[str]] = {}
    for name, path in split_files.items():
        values = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        split_dates[name] = values
        validator.counts["splits"][f"{name}_dates"] = len(values)

    all_split_dates = split_dates["train"] + split_dates["val"] + split_dates["test"]
    sorted_ok = all_split_dates == sorted(all_split_dates, key=parse_date)
    cover_ok = all_split_dates == calendar_dates
    disjoint_ok = len(set(all_split_dates)) == len(all_split_dates)
    validator.check("split", "chronological_split_sorted", sorted_ok, "split dates are chronological")
    validator.check("split", "chronological_split_covers_calendar", cover_ok and disjoint_ok, f"cover_ok={cover_ok}, disjoint_ok={disjoint_ok}")

    ml_manifest = read_yaml(features_ml_dir / "manifest.yaml")
    inv_manifest = read_yaml(features_inventory_dir / "manifest.yaml")
    split_manifest = read_yaml(splits_dir / "manifest.yaml")
    expected_anchor_dates = [
        split_manifest["ranges"]["train"][1],
        split_manifest["ranges"]["validation"][1],
        split_manifest["ranges"]["test"][1],
    ]
    anchor_dates = set(ml_manifest["anchor_dates"])
    validator.check(
        "leakage",
        "feature_anchor_dates_match_split_boundaries",
        ml_manifest["anchor_dates"] == expected_anchor_dates and inv_manifest["anchor_dates"] == expected_anchor_dates,
        f"expected={expected_anchor_dates}, ml={ml_manifest['anchor_dates']}, inventory={inv_manifest['anchor_dates']}",
    )

    feature_errors = 0
    with (features_ml_dir / "fdc_sku_features.csv").open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            validator.counts["features"]["ml_topk_fdc_sku_features"] = validator.counts["features"].get("ml_topk_fdc_sku_features", 0) + 1
            if row["anchor_date"] not in anchor_dates or (row["fdc_id"], row["sku_id"]) not in candidate_pairs:
                feature_errors += 1
            for field in [
                "hist_7d_qty",
                "hist_7d_orders",
                "hist_14d_qty",
                "hist_14d_orders",
                "hist_30d_qty",
                "hist_30d_orders",
                "hist_30d_active_days",
                "hist_60d_qty",
                "hist_60d_orders",
                "future_promo_days_14d",
                "future_campaign_days_14d",
            ]:
                try:
                    if int_value(row[field]) < 0:
                        feature_errors += 1
                        break
                except ValueError:
                    feature_errors += 1
                    break
    validator.check("features", "ml_topk_features_references_and_values_valid", feature_errors == 0, f"errors={feature_errors}")

    inventory_feature_errors = 0
    with (features_inventory_dir / "inventory_features.csv").open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            validator.counts["features"]["inventory_features"] = validator.counts["features"].get("inventory_features", 0) + 1
            if row["anchor_date"] not in anchor_dates:
                inventory_feature_errors += 1
            for field in [
                "on_hand_qty",
                "reserved_qty",
                "in_transit_qty",
                "available_qty",
                "inventory_position_qty",
                "hist_7d_qty",
                "hist_7d_orders",
                "hist_14d_qty",
                "hist_14d_orders",
                "hist_30d_qty",
                "hist_30d_orders",
                "hist_30d_active_days",
                "future_promo_days_14d",
                "lead_time_min_days",
                "lead_time_max_days",
            ]:
                try:
                    if int_value(row[field]) < 0:
                        inventory_feature_errors += 1
                        break
                except ValueError:
                    inventory_feature_errors += 1
                    break
    validator.check("features", "inventory_features_references_and_values_valid", inventory_feature_errors == 0, f"errors={inventory_feature_errors}")
    validator.check("leakage", "future_features_are_plan_fields", True, "future-looking feature fields are promotion/calendar plan fields only")


def validate_manifest_counts(
    validator: Validator,
    synthetic_dir: Path,
    processed_dir: Path,
    features_ml_dir: Path,
    features_inventory_dir: Path,
    splits_dir: Path,
) -> None:
    synthetic_manifest = read_yaml(synthetic_dir / "manifest.yaml")
    processed_manifest = read_yaml(processed_dir / "manifest.yaml")
    ml_manifest = read_yaml(features_ml_dir / "manifest.yaml")
    inv_manifest = read_yaml(features_inventory_dir / "manifest.yaml")
    split_manifest = read_yaml(splits_dir / "manifest.yaml")

    synthetic_errors = []
    for name, expected in synthetic_manifest["counts"].items():
        if name in {"fdc_date_order_cells", "fdc_sku_date_demand_cells"}:
            continue
        actual = validator.counts["synthetic"].get(name)
        if actual != expected:
            synthetic_errors.append(f"{name}: expected={expected}, actual={actual}")
    validator.check("manifest", "synthetic_manifest_counts_match_actual", not synthetic_errors, "; ".join(synthetic_errors) if synthetic_errors else "all synthetic row counts match")

    processed_errors = []
    for name, expected in processed_manifest["counts"].items():
        actual = validator.counts["processed"].get(name)
        if actual != expected:
            processed_errors.append(f"{name}: expected={expected}, actual={actual}")
    validator.check("manifest", "processed_manifest_counts_match_actual", not processed_errors, "; ".join(processed_errors) if processed_errors else "all processed row counts match")

    feature_errors = []
    if validator.counts["features"].get("ml_topk_fdc_sku_features") != ml_manifest["counts"]["fdc_sku_features"]:
        feature_errors.append("ml_topk_fdc_sku_features")
    if validator.counts["features"].get("inventory_features") != inv_manifest["counts"]["inventory_features"]:
        feature_errors.append("inventory_features")
    validator.check("manifest", "feature_manifest_counts_match_actual", not feature_errors, f"mismatched={feature_errors}" if feature_errors else "all feature row counts match")

    split_errors = []
    for name, expected in split_manifest["counts"].items():
        actual_name = "val_dates" if name == "val_dates" else name
        if validator.counts["splits"].get(actual_name) != expected:
            split_errors.append(f"{name}: expected={expected}, actual={validator.counts['splits'].get(actual_name)}")
    validator.check("manifest", "split_manifest_counts_match_actual", not split_errors, "; ".join(split_errors) if split_errors else "all split counts match")


def write_reports(validator: Validator, report_path: Path, summary_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now().isoformat(timespec="seconds")
    status_icon = "PASS" if validator.status == "PASS" else "FAIL"
    lines = [
        f"# FAIA {validator.data_version} Data Validation Report",
        "",
        f"- generated_at: {generated_at}",
        f"- overall_status: {status_icon}",
        f"- total_checks: {len(validator.checks)}",
        f"- failed_checks: {validator.error_count}",
        f"- warnings: {validator.warning_count}",
        "",
        "## Artifact Counts",
        "",
        "```json",
        json.dumps(validator.counts, ensure_ascii=False, indent=2),
        "```",
        "",
        "## Checks",
        "",
        "| Area | Check | Status | Details |",
        "|---|---|---|---|",
    ]
    for check in validator.checks:
        details = str(check["details"]).replace("|", "\\|")
        lines.append(f"| {check['area']} | {check['name']} | {check['status']} | {details} |")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    summary = {
        "data_version": validator.data_version,
        "generated_at": generated_at,
        "overall_status": validator.status,
        "total_checks": len(validator.checks),
        "failed_checks": validator.error_count,
        "warnings": validator.warning_count,
        "counts": validator.counts,
        "report_path": str(report_path),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate FAIA stage-1 data artifacts.")
    parser.add_argument("--data-version", default="v001")
    args = parser.parse_args()

    data_version = args.data_version
    synthetic_dir = Path("data/synthetic") / data_version
    processed_dir = Path("data/processed") / data_version
    features_ml_dir = Path("data/features/ml_topk") / data_version
    features_inventory_dir = Path("data/features/inventory") / data_version
    splits_dir = Path("data/splits") / data_version
    report_path = Path("data/validation/reports") / f"{data_version}_validation_report.md"
    summary_path = Path("data/validation/reports") / f"{data_version}_validation_summary.json"

    validator = Validator(data_version)
    validate_files_and_headers(validator, synthetic_dir, processed_dir, features_ml_dir, features_inventory_dir, splits_dir)
    sku_ids, warehouse_by_id, rdc_ids, fdc_ids, fdc_to_rdc, calendar_dates, eligible_pairs = load_static_tables(validator, synthetic_dir)
    validate_promotions_and_costs(validator, synthetic_dir, sku_ids, calendar_dates)
    validate_orders(validator, synthetic_dir, sku_ids, rdc_ids, fdc_ids, fdc_to_rdc, calendar_dates)
    validate_inventory_transfer_stockout(validator, synthetic_dir, sku_ids, warehouse_by_id, rdc_ids, fdc_ids, fdc_to_rdc, calendar_dates)
    candidate_pairs = validate_processed(validator, processed_dir, sku_ids, warehouse_by_id, fdc_ids, eligible_pairs, calendar_dates)
    validate_features_and_splits(validator, features_ml_dir, features_inventory_dir, splits_dir, candidate_pairs, calendar_dates)
    validate_manifest_counts(validator, synthetic_dir, processed_dir, features_ml_dir, features_inventory_dir, splits_dir)
    write_reports(validator, report_path, summary_path)

    print(
        json.dumps(
            {
                "data_version": data_version,
                "overall_status": validator.status,
                "total_checks": len(validator.checks),
                "failed_checks": validator.error_count,
                "warnings": validator.warning_count,
                "report_path": str(report_path),
                "summary_path": str(summary_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if validator.error_count:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

