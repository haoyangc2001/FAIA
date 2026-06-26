#!/usr/bin/env python3
"""Build processed tables, feature artifacts, and time splits for stage 1."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator

import yaml


def read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def write_csv(path: Path, fieldnames: list[str], rows: Iterator[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
            count += 1
    return count


def write_lines(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(manifest, f, sort_keys=False, allow_unicode=True)


@lru_cache(maxsize=None)
def parse_date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d")


def load_calendar(synthetic_dir: Path) -> list[str]:
    with (synthetic_dir / "calendar.csv").open("r", encoding="utf-8", newline="") as f:
        return [row["date"] for row in csv.DictReader(f)]


def build_time_splits(dates: list[str], config: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    split_cfg = config["split"]
    n = len(dates)
    train_end = round(n * float(split_cfg["train_ratio"]))
    val_end = train_end + round(n * float(split_cfg["validation_ratio"]))

    train_dates = dates[:train_end]
    val_dates = dates[train_end:val_end]
    test_dates = dates[val_end:]

    write_lines(output_dir / "train_dates.txt", train_dates)
    write_lines(output_dir / "val_dates.txt", val_dates)
    write_lines(output_dir / "test_dates.txt", test_dates)

    manifest = {
        "data_version": output_dir.name,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "split_method": "chronological",
        "counts": {
            "train_dates": len(train_dates),
            "val_dates": len(val_dates),
            "test_dates": len(test_dates),
        },
        "ranges": {
            "train": [train_dates[0], train_dates[-1]],
            "validation": [val_dates[0], val_dates[-1]],
            "test": [test_dates[0], test_dates[-1]],
        },
    }
    write_manifest(output_dir / "manifest.yaml", manifest)
    return manifest


def iter_order_baskets(
    orders_path: Path,
    order_items_path: Path,
) -> Iterator[tuple[dict[str, str], list[dict[str, str]]]]:
    with orders_path.open("r", encoding="utf-8", newline="") as orders_file, order_items_path.open(
        "r", encoding="utf-8", newline=""
    ) as items_file:
        orders = csv.DictReader(orders_file)
        items = csv.DictReader(items_file)
        current_item = next(items, None)
        for order in orders:
            order_id = order["order_id"]
            basket = []
            while current_item is not None and current_item["order_id"] == order_id:
                basket.append(current_item)
                current_item = next(items, None)
            if not basket:
                raise ValueError(f"Order has no items: {order_id}")
            yield order, basket


def build_order_processed_tables(
    synthetic_dir: Path,
    processed_dir: Path,
) -> tuple[dict[str, Any], dict[tuple[str, str], dict[str, Any]]]:
    demand_qty: Counter[tuple[str, str, str]] = Counter()
    demand_orders: Counter[tuple[str, str, str]] = Counter()
    order_types: dict[tuple[str, str], dict[str, Any]] = {}

    for order, basket in iter_order_baskets(synthetic_dir / "orders.csv", synthetic_dir / "order_items.csv"):
        date = order["order_date"]
        fdc_id = order["fdc_id"]
        quantities: dict[str, int] = {}
        for item in basket:
            sku_id = item["sku_id"]
            quantities[sku_id] = quantities.get(sku_id, 0) + int(item["qty"])

        for sku_id, qty in quantities.items():
            key = (date, fdc_id, sku_id)
            demand_qty[key] += qty
            demand_orders[key] += 1

        sku_ids = tuple(sorted(quantities))
        order_type_key = "|".join(sku_ids)
        type_key = (fdc_id, order_type_key)
        stats = order_types.get(type_key)
        if stats is None:
            stats = {
                "fdc_id": fdc_id,
                "order_type_key": order_type_key,
                "sku_ids": sku_ids,
                "sku_count": len(sku_ids),
                "order_count": 0,
                "total_qty": 0,
                "first_order_date": date,
                "last_order_date": date,
            }
            order_types[type_key] = stats
        stats["order_count"] += 1
        stats["total_qty"] += sum(quantities.values())
        if date < stats["first_order_date"]:
            stats["first_order_date"] = date
        if date > stats["last_order_date"]:
            stats["last_order_date"] = date

    demand_count = write_csv(
        processed_dir / "fdc_sku_daily_demand.csv",
        ["date", "fdc_id", "sku_id", "order_count", "demand_qty"],
        (
            {
                "date": date,
                "fdc_id": fdc_id,
                "sku_id": sku_id,
                "order_count": demand_orders[(date, fdc_id, sku_id)],
                "demand_qty": demand_qty[(date, fdc_id, sku_id)],
            }
            for date, fdc_id, sku_id in sorted(demand_qty)
        ),
    )

    sorted_type_keys = sorted(order_types)
    type_id_by_key: dict[tuple[str, str], str] = {}

    def order_type_rows() -> Iterator[dict[str, Any]]:
        for index, key in enumerate(sorted_type_keys, start=1):
            stats = order_types[key]
            order_type_id = f"OT{index:09d}"
            type_id_by_key[key] = order_type_id
            yield {
                "order_type_id": order_type_id,
                "fdc_id": stats["fdc_id"],
                "order_type_key": stats["order_type_key"],
                "sku_count": stats["sku_count"],
                "order_count": stats["order_count"],
                "total_qty": stats["total_qty"],
                "first_order_date": stats["first_order_date"],
                "last_order_date": stats["last_order_date"],
            }

    order_type_count = write_csv(
        processed_dir / "order_type_table.csv",
        [
            "order_type_id",
            "fdc_id",
            "order_type_key",
            "sku_count",
            "order_count",
            "total_qty",
            "first_order_date",
            "last_order_date",
        ],
        order_type_rows(),
    )

    def order_type_item_rows() -> Iterator[dict[str, Any]]:
        for key in sorted_type_keys:
            stats = order_types[key]
            order_type_id = type_id_by_key[key]
            for rank, sku_id in enumerate(stats["sku_ids"], start=1):
                yield {
                    "order_type_id": order_type_id,
                    "fdc_id": stats["fdc_id"],
                    "sku_id": sku_id,
                    "item_rank": rank,
                }

    order_type_item_count = write_csv(
        processed_dir / "order_type_items.csv",
        ["order_type_id", "fdc_id", "sku_id", "item_rank"],
        order_type_item_rows(),
    )

    demand_stats: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {"total_demand_qty": 0, "demand_order_count": 0, "active_demand_days": 0}
    )
    for (date, fdc_id, sku_id), qty in demand_qty.items():
        key = (fdc_id, sku_id)
        demand_stats[key]["total_demand_qty"] += qty
        demand_stats[key]["demand_order_count"] += demand_orders[(date, fdc_id, sku_id)]
        demand_stats[key]["active_demand_days"] += 1

    metrics = {
        "fdc_sku_daily_demand": demand_count,
        "order_type_table": order_type_count,
        "order_type_items": order_type_item_count,
    }
    return metrics, demand_stats


def load_sku_master(synthetic_dir: Path) -> dict[str, dict[str, str]]:
    with (synthetic_dir / "sku_master.csv").open("r", encoding="utf-8", newline="") as f:
        return {row["sku_id"]: row for row in csv.DictReader(f)}


def build_inventory_daily_state(synthetic_dir: Path, processed_dir: Path, anchor_dates: set[str]) -> tuple[int, list[dict[str, str]]]:
    anchor_inventory_rows: list[dict[str, str]] = []
    output_path = processed_dir / "inventory_daily_state.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with (synthetic_dir / "inventory_snapshot.csv").open("r", encoding="utf-8", newline="") as src, output_path.open(
        "w", encoding="utf-8", newline=""
    ) as dst:
        reader = csv.DictReader(src)
        fieldnames = [
            "date",
            "node_id",
            "node_type",
            "sku_id",
            "on_hand_qty",
            "reserved_qty",
            "in_transit_qty",
            "available_qty",
            "inventory_position_qty",
        ]
        writer = csv.DictWriter(dst, fieldnames=fieldnames)
        writer.writeheader()
        count = 0
        for row in reader:
            on_hand = int(row["on_hand_qty"])
            reserved = int(row["reserved_qty"])
            in_transit = int(row["in_transit_qty"])
            output = {
                "date": row["date"],
                "node_id": row["node_id"],
                "node_type": row["node_type"],
                "sku_id": row["sku_id"],
                "on_hand_qty": on_hand,
                "reserved_qty": reserved,
                "in_transit_qty": in_transit,
                "available_qty": max(0, on_hand - reserved),
                "inventory_position_qty": max(0, on_hand - reserved) + in_transit,
            }
            writer.writerow(output)
            count += 1
            if row["date"] in anchor_dates and row["node_type"] == "FDC":
                anchor_inventory_rows.append({k: str(v) for k, v in output.items()})
    return count, anchor_inventory_rows


def build_candidate_pool_base(
    synthetic_dir: Path,
    processed_dir: Path,
    sku_master: dict[str, dict[str, str]],
    demand_stats: dict[tuple[str, str], dict[str, Any]],
) -> tuple[int, list[dict[str, Any]]]:
    candidates: list[dict[str, Any]] = []
    with (synthetic_dir / "sku_fdc_eligibility.csv").open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row["eligible_flag"] != "true":
                continue
            sku = sku_master[row["sku_id"]]
            stats = demand_stats.get(
                (row["fdc_id"], row["sku_id"]),
                {"total_demand_qty": 0, "demand_order_count": 0, "active_demand_days": 0},
            )
            candidates.append(
                {
                    "fdc_id": row["fdc_id"],
                    "sku_id": row["sku_id"],
                    "rdc_id": row["rdc_id"],
                    "eligible_flag": row["eligible_flag"],
                    "category_id": sku["category_id"],
                    "brand_id": sku["brand_id"],
                    "temperature_zone": sku["temperature_zone"],
                    "price": sku["price"],
                    "volume": sku["volume"],
                    "weight": sku["weight"],
                    "shelf_life_days": sku["shelf_life_days"],
                    "is_regular_product": sku["is_regular_product"],
                    "base_popularity": sku["base_popularity"],
                    "total_demand_qty": stats["total_demand_qty"],
                    "demand_order_count": stats["demand_order_count"],
                    "active_demand_days": stats["active_demand_days"],
                }
            )

    count = write_csv(
        processed_dir / "candidate_pool_base.csv",
        [
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
        iter(candidates),
    )
    return count, candidates


def load_daily_demand(processed_dir: Path) -> dict[tuple[str, str], list[tuple[str, int, int]]]:
    demand: dict[tuple[str, str], list[tuple[str, int, int]]] = defaultdict(list)
    with (processed_dir / "fdc_sku_daily_demand.csv").open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            demand[(row["fdc_id"], row["sku_id"])].append(
                (row["date"], int(row["demand_qty"]), int(row["order_count"]))
            )
    for rows in demand.values():
        rows.sort(key=lambda item: item[0])
    return demand


def load_promotion_dates(synthetic_dir: Path) -> dict[str, set[str]]:
    dates: dict[str, set[str]] = defaultdict(set)
    with (synthetic_dir / "promotion_plan.csv").open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            dates[row["sku_id"]].add(row["date"])
    return dates


def load_campaign_dates(synthetic_dir: Path) -> set[str]:
    campaign_dates = set()
    with (synthetic_dir / "calendar.csv").open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row["campaign_window"]:
                campaign_dates.add(row["date"])
    return campaign_dates


def window_stats(rows: list[tuple[str, int, int]], anchor_date: str, days: int) -> tuple[int, int, int]:
    anchor = parse_date(anchor_date)
    start = anchor - timedelta(days=days - 1)
    qty = 0
    orders = 0
    active_days = 0
    for row_date, row_qty, row_orders in rows:
        current = parse_date(row_date)
        if start <= current <= anchor:
            qty += row_qty
            orders += row_orders
            active_days += 1
    return qty, orders, active_days


def future_count(date_set: set[str], anchor_date: str, days: int) -> int:
    anchor = parse_date(anchor_date)
    end = anchor + timedelta(days=days)
    return sum(1 for value in date_set if anchor < parse_date(value) <= end)


def build_feature_artifacts(
    synthetic_dir: Path,
    processed_dir: Path,
    features_dir: Path,
    candidates: list[dict[str, Any]],
    anchor_dates: list[str],
    anchor_inventory_rows: list[dict[str, str]],
    config: dict[str, Any],
) -> dict[str, Any]:
    demand = load_daily_demand(processed_dir)
    promotion_dates = load_promotion_dates(synthetic_dir)
    campaign_dates = load_campaign_dates(synthetic_dir)

    ml_dir = features_dir / "ml_topk" / processed_dir.name
    inv_dir = features_dir / "inventory" / processed_dir.name

    def ml_rows() -> Iterator[dict[str, Any]]:
        for anchor_date in anchor_dates:
            campaign_next_14d = future_count(campaign_dates, anchor_date, 14)
            for candidate in candidates:
                key = (candidate["fdc_id"], candidate["sku_id"])
                rows = demand.get(key, [])
                hist_7_qty, hist_7_orders, _ = window_stats(rows, anchor_date, 7)
                hist_14_qty, hist_14_orders, _ = window_stats(rows, anchor_date, 14)
                hist_30_qty, hist_30_orders, hist_active_30d = window_stats(rows, anchor_date, 30)
                hist_60_qty, hist_60_orders, _ = window_stats(rows, anchor_date, 60)
                yield {
                    "anchor_date": anchor_date,
                    "fdc_id": candidate["fdc_id"],
                    "sku_id": candidate["sku_id"],
                    "category_id": candidate["category_id"],
                    "brand_id": candidate["brand_id"],
                    "temperature_zone": candidate["temperature_zone"],
                    "base_popularity": candidate["base_popularity"],
                    "price": candidate["price"],
                    "is_regular_product": candidate["is_regular_product"],
                    "hist_7d_qty": hist_7_qty,
                    "hist_7d_orders": hist_7_orders,
                    "hist_14d_qty": hist_14_qty,
                    "hist_14d_orders": hist_14_orders,
                    "hist_30d_qty": hist_30_qty,
                    "hist_30d_orders": hist_30_orders,
                    "hist_30d_active_days": hist_active_30d,
                    "hist_60d_qty": hist_60_qty,
                    "hist_60d_orders": hist_60_orders,
                    "future_promo_days_14d": future_count(promotion_dates.get(candidate["sku_id"], set()), anchor_date, 14),
                    "future_campaign_days_14d": campaign_next_14d,
                }

    ml_count = write_csv(
        ml_dir / "fdc_sku_features.csv",
        [
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
        ml_rows(),
    )

    def inventory_rows() -> Iterator[dict[str, Any]]:
        for row in anchor_inventory_rows:
            if row["node_type"] != "FDC":
                continue
            key = (row["node_id"], row["sku_id"])
            demand_rows = demand.get(key, [])
            hist_7_qty, hist_7_orders, _ = window_stats(demand_rows, row["date"], 7)
            hist_14_qty, hist_14_orders, _ = window_stats(demand_rows, row["date"], 14)
            hist_30_qty, hist_30_orders, hist_active_30d = window_stats(demand_rows, row["date"], 30)
            yield {
                "anchor_date": row["date"],
                "fdc_id": row["node_id"],
                "sku_id": row["sku_id"],
                "on_hand_qty": row["on_hand_qty"],
                "reserved_qty": row["reserved_qty"],
                "in_transit_qty": row["in_transit_qty"],
                "available_qty": row["available_qty"],
                "inventory_position_qty": row["inventory_position_qty"],
                "hist_7d_qty": hist_7_qty,
                "hist_7d_orders": hist_7_orders,
                "hist_14d_qty": hist_14_qty,
                "hist_14d_orders": hist_14_orders,
                "hist_30d_qty": hist_30_qty,
                "hist_30d_orders": hist_30_orders,
                "hist_30d_active_days": hist_active_30d,
                "future_promo_days_14d": future_count(promotion_dates.get(row["sku_id"], set()), row["date"], 14),
                "lead_time_min_days": config["inventory"]["lead_time_min_days"],
                "lead_time_max_days": config["inventory"]["lead_time_max_days"],
            }

    inventory_count = write_csv(
        inv_dir / "inventory_features.csv",
        [
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
        inventory_rows(),
    )

    ml_manifest = {
        "data_version": processed_dir.name,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "anchor_dates": anchor_dates,
        "counts": {"fdc_sku_features": ml_count},
    }
    inventory_manifest = {
        "data_version": processed_dir.name,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "anchor_dates": anchor_dates,
        "counts": {"inventory_features": inventory_count},
    }
    write_manifest(ml_dir / "manifest.yaml", ml_manifest)
    write_manifest(inv_dir / "manifest.yaml", inventory_manifest)

    return {
        "ml_topk_fdc_sku_features": ml_count,
        "inventory_features": inventory_count,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build stage-1 processed, feature, and split artifacts.")
    parser.add_argument("--config", default="data/configs/synthetic_small.yaml")
    parser.add_argument("--data-version", default="v001")
    args = parser.parse_args()

    config = read_yaml(Path(args.config))
    data_version = args.data_version
    synthetic_dir = Path("data/synthetic") / data_version
    processed_dir = Path("data/processed") / data_version
    features_dir = Path("data/features")
    splits_dir = Path("data/splits") / data_version

    dates = load_calendar(synthetic_dir)
    split_manifest = build_time_splits(dates, config, splits_dir)
    anchor_dates = [
        split_manifest["ranges"]["train"][1],
        split_manifest["ranges"]["validation"][1],
        split_manifest["ranges"]["test"][1],
    ]
    anchor_date_set = set(anchor_dates)

    order_metrics, demand_stats = build_order_processed_tables(synthetic_dir, processed_dir)
    sku_master = load_sku_master(synthetic_dir)
    inventory_count, anchor_inventory_rows = build_inventory_daily_state(synthetic_dir, processed_dir, anchor_date_set)
    candidate_count, candidates = build_candidate_pool_base(synthetic_dir, processed_dir, sku_master, demand_stats)
    feature_metrics = build_feature_artifacts(
        synthetic_dir,
        processed_dir,
        features_dir,
        candidates,
        anchor_dates,
        anchor_inventory_rows,
        config,
    )

    processed_manifest = {
        "data_version": data_version,
        "source_synthetic_dir": str(synthetic_dir),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "counts": {
            **order_metrics,
            "inventory_daily_state": inventory_count,
            "candidate_pool_base": candidate_count,
        },
    }
    write_manifest(processed_dir / "manifest.yaml", processed_manifest)

    summary = {
        "processed": processed_manifest,
        "features": feature_metrics,
        "splits": split_manifest,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
