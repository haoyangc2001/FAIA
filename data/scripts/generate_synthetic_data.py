#!/usr/bin/env python3
"""Generate the first synthetic FAIA business world.

The generator creates stage-1 raw synthetic tables:

- sku_master.csv
- warehouse_master.csv
- sku_fdc_eligibility.csv
- calendar.csv
- promotion_plan.csv
- orders.csv
- order_items.csv
- inventory_snapshot.csv
- transfer_plan.csv
- stockout_events.csv
- cost_config.csv
- manifest.yaml
"""

from __future__ import annotations

import argparse
import csv
import math
import random
from bisect import bisect_left
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

import yaml


BOOL_TRUE = "true"
BOOL_FALSE = "false"


@dataclass(frozen=True)
class Sampler:
    items: list[str]
    cumulative_weights: list[float]

    @property
    def total(self) -> float:
        return self.cumulative_weights[-1]


def bool_text(value: bool) -> str:
    return BOOL_TRUE if value else BOOL_FALSE


def read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
            count += 1
    return count


def build_sampler(items: list[str], weights: list[float]) -> Sampler:
    cumulative = []
    total = 0.0
    for weight in weights:
        total += max(float(weight), 0.0000001)
        cumulative.append(total)
    return Sampler(items=items, cumulative_weights=cumulative)


def sample_one(rng: random.Random, sampler: Sampler) -> str:
    point = rng.random() * sampler.total
    return sampler.items[bisect_left(sampler.cumulative_weights, point)]


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def date_text(value: date) -> str:
    return value.isoformat()


def weighted_temperature_zone(rng: random.Random, weights: dict[str, float]) -> str:
    zones = list(weights)
    sampler = build_sampler(zones, [weights[zone] for zone in zones])
    return sample_one(rng, sampler)


def campaign_info(current: date) -> tuple[str, str]:
    windows = [
        ("new_year", date(2026, 1, 1), date(2026, 1, 1)),
        ("spring_festival", date(2026, 2, 13), date(2026, 2, 22)),
        ("labor_day", date(2026, 5, 1), date(2026, 5, 5)),
        ("mid_year_618", date(2026, 6, 1), date(2026, 6, 18)),
    ]
    for name, start, end in windows:
        if start <= current <= end:
            span = (end - start).days + 1
            offset = (current - start).days
            if span == 1:
                return name, "peak"
            if offset < max(1, span // 3):
                return name, "warmup"
            if offset < max(2, span * 2 // 3):
                return name, "peak"
            return name, "cooldown"
    return "", ""


def generate_skus(config: dict[str, Any], rng: random.Random) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    catalog = config["catalog"]
    temp_weights = config["network"]["temperature_zones"]
    num_skus = int(catalog["num_skus"])
    num_categories = int(catalog["num_categories"])
    num_brands = int(catalog["num_brands"])
    alpha = float(catalog["zipf_alpha"])
    regular_ratio = float(catalog["regular_product_ratio"])

    rows: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    for rank in range(1, num_skus + 1):
        sku_id = f"SKU{rank:06d}"
        category_id = f"CAT{rng.randint(1, num_categories):03d}"
        brand_id = f"BR{rng.randint(1, num_brands):04d}"
        zone = weighted_temperature_zone(rng, temp_weights)
        base_popularity = 1.0 / math.pow(rank, alpha)
        if zone == "ambient":
            shelf_life = rng.randint(30, 365)
        elif zone == "chilled":
            shelf_life = rng.randint(5, 21)
        else:
            shelf_life = rng.randint(30, 180)

        price = round(max(1.0, rng.lognormvariate(3.0, 0.6)), 2)
        volume = round(rng.uniform(0.05, 3.0), 4)
        weight = round(rng.uniform(0.05, 5.0), 4)
        row = {
            "sku_id": sku_id,
            "category_id": category_id,
            "brand_id": brand_id,
            "price": price,
            "temperature_zone": zone,
            "volume": volume,
            "weight": weight,
            "shelf_life_days": shelf_life,
            "is_regular_product": bool_text(rng.random() < regular_ratio),
            "base_popularity": round(base_popularity, 10),
        }
        rows.append(row)
        by_id[sku_id] = row
    return rows, by_id


def generate_warehouses(config: dict[str, Any], rng: random.Random) -> tuple[list[dict[str, Any]], list[str], list[str], dict[str, str]]:
    network = config["network"]
    num_rdcs = int(network["num_rdcs"])
    num_fdcs = int(network["num_fdcs"])
    cap_min = int(network["fdc_capacity_min"])
    cap_max = int(network["fdc_capacity_max"])

    rows: list[dict[str, Any]] = []
    rdc_ids = [f"RDC{i:03d}" for i in range(1, num_rdcs + 1)]
    fdc_ids = [f"FDC{i:03d}" for i in range(1, num_fdcs + 1)]
    fdc_to_rdc: dict[str, str] = {}

    for index, rdc_id in enumerate(rdc_ids, start=1):
        rows.append(
            {
                "node_id": rdc_id,
                "node_type": "RDC",
                "rdc_id": "",
                "city_id": f"CITY{index:02d}",
                "region_id": f"REGION_RDC_{index:02d}",
                "capacity_units": cap_max * num_fdcs * 3,
                "support_ambient": BOOL_TRUE,
                "support_chilled": BOOL_TRUE,
                "support_frozen": BOOL_TRUE,
            }
        )

    for index, fdc_id in enumerate(fdc_ids, start=1):
        rdc_id = rdc_ids[(index - 1) % len(rdc_ids)]
        fdc_to_rdc[fdc_id] = rdc_id
        supports_chilled = rng.random() < 0.85
        supports_frozen = rng.random() < 0.45
        rows.append(
            {
                "node_id": fdc_id,
                "node_type": "FDC",
                "rdc_id": rdc_id,
                "city_id": f"CITY{((index - 1) % len(rdc_ids)) + 1:02d}",
                "region_id": f"REGION_FDC_{index:03d}",
                "capacity_units": rng.randint(cap_min, cap_max),
                "support_ambient": BOOL_TRUE,
                "support_chilled": bool_text(supports_chilled),
                "support_frozen": bool_text(supports_frozen),
            }
        )
    return rows, rdc_ids, fdc_ids, fdc_to_rdc


def generate_eligibility(
    skus: list[dict[str, Any]],
    warehouses: list[dict[str, Any]],
    fdc_to_rdc: dict[str, str],
    rng: random.Random,
) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    fdc_rows = [row for row in warehouses if row["node_type"] == "FDC"]
    eligible_by_fdc: dict[str, list[str]] = {row["node_id"]: [] for row in fdc_rows}
    rows: list[dict[str, Any]] = []

    for fdc in fdc_rows:
        fdc_id = fdc["node_id"]
        supports = {
            "ambient": fdc["support_ambient"] == BOOL_TRUE,
            "chilled": fdc["support_chilled"] == BOOL_TRUE,
            "frozen": fdc["support_frozen"] == BOOL_TRUE,
        }
        for sku in skus:
            zone = str(sku["temperature_zone"])
            random_region_limit = rng.random() < 0.03
            eligible = supports[zone] and not random_region_limit
            reason = ""
            if not supports[zone]:
                reason = "temperature_zone_not_supported"
            elif random_region_limit:
                reason = "regional_restriction"
            if eligible:
                eligible_by_fdc[fdc_id].append(str(sku["sku_id"]))
            rows.append(
                {
                    "sku_id": sku["sku_id"],
                    "fdc_id": fdc_id,
                    "rdc_id": fdc_to_rdc[fdc_id],
                    "eligible_flag": bool_text(eligible),
                    "ineligible_reason": reason,
                }
            )
    return rows, eligible_by_fdc


def generate_calendar(config: dict[str, Any]) -> list[dict[str, Any]]:
    calendar_cfg = config["calendar"]
    current = parse_date(str(calendar_cfg["start_date"]))
    num_days = int(calendar_cfg["num_days"])
    rows = []
    holiday_dates = {
        date(2026, 1, 1),
        date(2026, 2, 17),
        date(2026, 2, 18),
        date(2026, 2, 19),
        date(2026, 5, 1),
        date(2026, 5, 2),
        date(2026, 5, 3),
    }

    for offset in range(num_days):
        day = current + timedelta(days=offset)
        window, phase = campaign_info(day)
        day_of_week = day.isoweekday()
        is_weekend = day_of_week >= 6
        is_holiday = day in holiday_dates
        multiplier = 1.0
        if is_weekend:
            multiplier *= 1.08
        if is_holiday:
            multiplier *= 1.20
        if phase == "warmup":
            multiplier *= 1.12
        elif phase == "peak":
            multiplier *= 1.35
        elif phase == "cooldown":
            multiplier *= 1.08
        rows.append(
            {
                "date": date_text(day),
                "day_of_week": day_of_week,
                "is_weekend": bool_text(is_weekend),
                "is_holiday": bool_text(is_holiday),
                "campaign_window": window,
                "campaign_phase": phase,
                "demand_multiplier": round(multiplier, 4),
            }
        )
    return rows


def generate_promotions(
    config: dict[str, Any],
    skus: list[dict[str, Any]],
    calendar_rows: list[dict[str, Any]],
    rng: random.Random,
) -> tuple[list[dict[str, Any]], dict[str, list[tuple[str, float]]]]:
    promo_cfg = config["promotion"]
    promoted_count = max(1, int(len(skus) * float(promo_cfg["promoted_sku_ratio"])))
    promoted_skus = rng.sample([str(row["sku_id"]) for row in skus], promoted_count)
    promotion_types = list(promo_cfg["promotion_types"])
    lift_min = float(promo_cfg["demand_lift_min"])
    lift_max = float(promo_cfg["demand_lift_max"])

    rows: list[dict[str, Any]] = []
    by_date: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for cal in calendar_rows:
        if not cal["campaign_window"]:
            continue
        phase = str(cal["campaign_phase"])
        active_ratio = 0.35 if phase == "warmup" else 0.55 if phase == "peak" else 0.25
        active_count = max(1, int(len(promoted_skus) * active_ratio))
        active_skus = rng.sample(promoted_skus, active_count)
        for sku_id in active_skus:
            if phase == "peak":
                lift = rng.uniform((lift_min + lift_max) / 2, lift_max)
            else:
                lift = rng.uniform(lift_min, (lift_min + lift_max) / 2)
            row = {
                "date": cal["date"],
                "sku_id": sku_id,
                "promotion_type": rng.choice(promotion_types),
                "discount_rate": round(rng.uniform(0.05, 0.35), 4),
                "coupon_value": round(rng.choice([0, 2, 5, 10, 15]), 2),
                "planned_exposure_level": rng.randint(1, 5),
                "campaign_phase": phase,
                "planned_demand_lift": round(lift, 4),
            }
            rows.append(row)
            by_date[str(cal["date"])].append((sku_id, float(row["planned_demand_lift"])))
    return rows, by_date


def build_order_samplers(
    skus_by_id: dict[str, dict[str, Any]],
    eligible_by_fdc: dict[str, list[str]],
    fdc_ids: list[str],
    config: dict[str, Any],
    rng: random.Random,
) -> tuple[dict[str, Sampler], dict[tuple[str, str], Sampler], dict[tuple[str, str], Sampler], dict[str, list[str]]]:
    orders_cfg = config["orders"]
    category_strength = float(orders_cfg["category_preference_strength"])
    regional_strength = float(orders_cfg["regional_preference_strength"])
    samplers: dict[str, Sampler] = {}
    category_samplers: dict[tuple[str, str], Sampler] = {}
    brand_samplers: dict[tuple[str, str], Sampler] = {}
    fdc_preferred_categories: dict[str, list[str]] = {}

    all_categories = sorted({str(row["category_id"]) for row in skus_by_id.values()})
    for fdc_id in fdc_ids:
        preferred_categories = rng.sample(all_categories, min(6, len(all_categories)))
        fdc_preferred_categories[fdc_id] = preferred_categories
        items = eligible_by_fdc[fdc_id]
        weights = []
        category_items: dict[str, list[str]] = defaultdict(list)
        category_weights: dict[str, list[float]] = defaultdict(list)
        brand_items: dict[str, list[str]] = defaultdict(list)
        brand_weights: dict[str, list[float]] = defaultdict(list)

        for sku_id in items:
            sku = skus_by_id[sku_id]
            base = float(sku["base_popularity"])
            category_id = str(sku["category_id"])
            brand_id = str(sku["brand_id"])
            weight = base
            if category_id in preferred_categories:
                weight *= 1.0 + category_strength
            weight *= rng.uniform(1.0 - regional_strength / 2, 1.0 + regional_strength)
            weights.append(weight)
            category_items[category_id].append(sku_id)
            category_weights[category_id].append(weight)
            brand_items[brand_id].append(sku_id)
            brand_weights[brand_id].append(weight)

        samplers[fdc_id] = build_sampler(items, weights)
        for category_id, category_sku_ids in category_items.items():
            category_samplers[(fdc_id, category_id)] = build_sampler(
                category_sku_ids, category_weights[category_id]
            )
        for brand_id, brand_sku_ids in brand_items.items():
            brand_samplers[(fdc_id, brand_id)] = build_sampler(brand_sku_ids, brand_weights[brand_id])
    return samplers, category_samplers, brand_samplers, fdc_preferred_categories


def choose_sku_for_order(
    rng: random.Random,
    fdc_id: str,
    date_key: str,
    samplers: dict[str, Sampler],
    promotion_by_date: dict[str, list[tuple[str, float]]],
    eligible_sets: dict[str, set[str]],
) -> str:
    promos = promotion_by_date.get(date_key, [])
    if promos and rng.random() < 0.18:
        eligible_promos = [sku_id for sku_id, _ in promos if sku_id in eligible_sets[fdc_id]]
        if eligible_promos:
            return rng.choice(eligible_promos)
    return sample_one(rng, samplers[fdc_id])


def choose_basket_item(
    rng: random.Random,
    fdc_id: str,
    anchor_sku_id: str,
    skus_by_id: dict[str, dict[str, Any]],
    samplers: dict[str, Sampler],
    category_samplers: dict[tuple[str, str], Sampler],
    brand_samplers: dict[tuple[str, str], Sampler],
    basket_affinity_strength: float,
) -> str:
    anchor = skus_by_id[anchor_sku_id]
    if rng.random() < basket_affinity_strength:
        category_key = (fdc_id, str(anchor["category_id"]))
        if category_key in category_samplers:
            return sample_one(rng, category_samplers[category_key])
    if rng.random() < basket_affinity_strength / 2:
        brand_key = (fdc_id, str(anchor["brand_id"]))
        if brand_key in brand_samplers:
            return sample_one(rng, brand_samplers[brand_key])
    return sample_one(rng, samplers[fdc_id])


def sample_item_count(rng: random.Random, max_items: int) -> int:
    point = rng.random()
    if point < 0.72:
        return 2
    if point < 0.92:
        return min(3, max_items)
    return rng.randint(4, max_items) if max_items >= 4 else max_items


def generate_orders(
    config: dict[str, Any],
    output_dir: Path,
    calendar_rows: list[dict[str, Any]],
    skus_by_id: dict[str, dict[str, Any]],
    fdc_ids: list[str],
    fdc_to_rdc: dict[str, str],
    eligible_by_fdc: dict[str, list[str]],
    promotion_by_date: dict[str, list[tuple[str, float]]],
    rng: random.Random,
) -> tuple[int, int, Counter[tuple[str, str, str]], Counter[tuple[str, str]]]:
    orders_cfg = config["orders"]
    min_orders = int(orders_cfg["daily_order_min"])
    max_orders = int(orders_cfg["daily_order_max"])
    multi_ratio = float(orders_cfg["multi_item_order_ratio"])
    max_items = int(orders_cfg["max_items_per_order"])
    basket_affinity_strength = float(orders_cfg["basket_affinity_strength"])

    samplers, category_samplers, brand_samplers, _ = build_order_samplers(
        skus_by_id, eligible_by_fdc, fdc_ids, config, rng
    )
    eligible_sets = {fdc_id: set(sku_ids) for fdc_id, sku_ids in eligible_by_fdc.items()}
    fdc_sampler = build_sampler(fdc_ids, [rng.uniform(0.8, 1.2) for _ in fdc_ids])

    orders_path = output_dir / "orders.csv"
    items_path = output_dir / "order_items.csv"
    demand = Counter()
    fdc_date_orders = Counter()
    order_count = 0
    item_count = 0

    with orders_path.open("w", encoding="utf-8", newline="") as orders_file, items_path.open(
        "w", encoding="utf-8", newline=""
    ) as items_file:
        order_writer = csv.DictWriter(
            orders_file,
            fieldnames=[
                "order_id",
                "order_date",
                "rdc_id",
                "fdc_id",
                "user_region_id",
                "order_item_count",
                "is_multi_item",
            ],
        )
        item_writer = csv.DictWriter(
            items_file,
            fieldnames=["order_id", "sku_id", "qty", "unit_price"],
        )
        order_writer.writeheader()
        item_writer.writeheader()

        for cal in calendar_rows:
            date_key = str(cal["date"])
            daily_total = int(rng.randint(min_orders, max_orders) * float(cal["demand_multiplier"]))
            for _ in range(daily_total):
                fdc_id = sample_one(rng, fdc_sampler)
                rdc_id = fdc_to_rdc[fdc_id]
                is_multi = rng.random() < multi_ratio
                target_items = sample_item_count(rng, max_items) if is_multi else 1
                first_sku = choose_sku_for_order(
                    rng,
                    fdc_id,
                    date_key,
                    samplers,
                    promotion_by_date,
                    eligible_sets,
                )
                quantities: dict[str, int] = {first_sku: 1}
                attempts = 0
                while len(quantities) < target_items:
                    attempts += 1
                    next_sku = choose_basket_item(
                        rng,
                        fdc_id,
                        first_sku,
                        skus_by_id,
                        samplers,
                        category_samplers,
                        brand_samplers,
                        basket_affinity_strength,
                    )
                    if next_sku in quantities:
                        if quantities[next_sku] < 3 and rng.random() < 0.10:
                            quantities[next_sku] += 1
                    else:
                        quantities[next_sku] = 1
                    if len(quantities) >= len(eligible_by_fdc[fdc_id]) or attempts > target_items * 20:
                        break

                order_count += 1
                order_id = f"O{order_count:010d}"
                order_writer.writerow(
                    {
                        "order_id": order_id,
                        "order_date": date_key,
                        "rdc_id": rdc_id,
                        "fdc_id": fdc_id,
                        "user_region_id": f"USER_REGION_{fdc_id[-3:]}",
                        "order_item_count": len(quantities),
                        "is_multi_item": bool_text(len(quantities) > 1),
                    }
                )
                fdc_date_orders[(date_key, fdc_id)] += 1
                for sku_id, qty in quantities.items():
                    sku = skus_by_id[sku_id]
                    item_writer.writerow(
                        {
                            "order_id": order_id,
                            "sku_id": sku_id,
                            "qty": qty,
                            "unit_price": sku["price"],
                        }
                    )
                    item_count += 1
                    demand[(date_key, fdc_id, sku_id)] += qty

    return order_count, item_count, demand, fdc_date_orders


def choose_initial_fdc_assortment(
    warehouses: list[dict[str, Any]],
    skus_by_id: dict[str, dict[str, Any]],
    eligible_by_fdc: dict[str, list[str]],
) -> dict[str, set[str]]:
    fdc_rows = [row for row in warehouses if row["node_type"] == "FDC"]
    assortment: dict[str, set[str]] = {}
    for fdc in fdc_rows:
        fdc_id = str(fdc["node_id"])
        capacity = int(fdc["capacity_units"])
        eligible = eligible_by_fdc[fdc_id]
        ranked = sorted(eligible, key=lambda sku_id: float(skus_by_id[sku_id]["base_popularity"]), reverse=True)
        assortment[fdc_id] = set(ranked[: min(capacity, len(ranked))])
    return assortment


def generate_inventory_tables(
    config: dict[str, Any],
    output_dir: Path,
    calendar_rows: list[dict[str, Any]],
    warehouses: list[dict[str, Any]],
    skus_by_id: dict[str, dict[str, Any]],
    fdc_ids: list[str],
    rdc_ids: list[str],
    fdc_to_rdc: dict[str, str],
    eligible_by_fdc: dict[str, list[str]],
    demand: Counter[tuple[str, str, str]],
    rng: random.Random,
) -> tuple[int, int, int, int]:
    inventory_cfg = config["inventory"]
    cost_cfg = config["cost"]
    fdc_days = int(inventory_cfg["fdc_initial_days_of_supply"])
    rdc_days = int(inventory_cfg["rdc_initial_days_of_supply"])
    lead_min = int(inventory_cfg["lead_time_min_days"])
    lead_max = int(inventory_cfg["lead_time_max_days"])
    num_days = len(calendar_rows)

    assortment = choose_initial_fdc_assortment(warehouses, skus_by_id, eligible_by_fdc)
    demand_total_by_fdc_sku = Counter()
    demand_total_by_rdc_sku = Counter()
    demand_by_date_fdc: dict[tuple[str, str], list[tuple[str, int]]] = defaultdict(list)
    for (_, fdc_id, sku_id), qty in demand.items():
        demand_total_by_fdc_sku[(fdc_id, sku_id)] += qty
        demand_total_by_rdc_sku[(fdc_to_rdc[fdc_id], sku_id)] += qty
    for (date_key, fdc_id, sku_id), qty in demand.items():
        demand_by_date_fdc[(date_key, fdc_id)].append((sku_id, qty))

    fdc_stock: dict[tuple[str, str], int] = {}
    rdc_stock: dict[tuple[str, str], int] = {}
    outstanding: Counter[tuple[str, str]] = Counter()
    arrivals: dict[str, Counter[tuple[str, str]]] = defaultdict(Counter)

    for fdc_id in fdc_ids:
        for sku_id in assortment[fdc_id]:
            avg = demand_total_by_fdc_sku[(fdc_id, sku_id)] / max(num_days, 1)
            fdc_stock[(fdc_id, sku_id)] = max(2, math.ceil(avg * fdc_days * rng.uniform(0.7, 1.3)))

    for rdc_id in rdc_ids:
        for sku_id in skus_by_id:
            avg = demand_total_by_rdc_sku[(rdc_id, sku_id)] / max(num_days, 1)
            rdc_stock[(rdc_id, sku_id)] = max(5, math.ceil(avg * rdc_days * rng.uniform(1.1, 1.6)))

    snapshot_path = output_dir / "inventory_snapshot.csv"
    transfer_path = output_dir / "transfer_plan.csv"
    stockout_path = output_dir / "stockout_events.csv"
    cost_path = output_dir / "cost_config.csv"

    snapshot_count = 0
    transfer_count = 0
    stockout_count = 0

    with snapshot_path.open("w", encoding="utf-8", newline="") as snapshot_file, transfer_path.open(
        "w", encoding="utf-8", newline=""
    ) as transfer_file, stockout_path.open("w", encoding="utf-8", newline="") as stockout_file:
        snapshot_writer = csv.DictWriter(
            snapshot_file,
            fieldnames=["date", "node_id", "node_type", "sku_id", "on_hand_qty", "reserved_qty", "in_transit_qty"],
        )
        transfer_writer = csv.DictWriter(
            transfer_file,
            fieldnames=[
                "transfer_id",
                "ship_date",
                "arrival_date",
                "rdc_id",
                "fdc_id",
                "sku_id",
                "transfer_qty",
                "lead_time_days",
            ],
        )
        stockout_writer = csv.DictWriter(
            stockout_file,
            fieldnames=["date", "node_id", "node_type", "sku_id", "stockout_flag", "stockout_qty", "stockout_reason"],
        )
        snapshot_writer.writeheader()
        transfer_writer.writeheader()
        stockout_writer.writeheader()

        for cal in calendar_rows:
            date_key = str(cal["date"])
            arrived = arrivals.get(date_key, Counter())
            for (fdc_id, sku_id), qty in arrived.items():
                fdc_stock[(fdc_id, sku_id)] += qty
                outstanding[(fdc_id, sku_id)] -= qty

            transfer_requests: list[tuple[str, str, int]] = []
            for fdc_id in fdc_ids:
                for sku_id in assortment[fdc_id]:
                    key = (fdc_id, sku_id)
                    day_demand = demand[(date_key, fdc_id, sku_id)]
                    current_stock = fdc_stock[key]
                    if day_demand > current_stock:
                        stockout_qty = day_demand - current_stock
                        stockout_writer.writerow(
                            {
                                "date": date_key,
                                "node_id": fdc_id,
                                "node_type": "FDC",
                                "sku_id": sku_id,
                                "stockout_flag": BOOL_TRUE,
                                "stockout_qty": stockout_qty,
                                "stockout_reason": "insufficient_fdc_inventory",
                            }
                        )
                        stockout_count += 1
                        fdc_stock[key] = 0
                    else:
                        fdc_stock[key] = current_stock - day_demand

                    avg_daily = demand_total_by_fdc_sku[key] / max(num_days, 1)
                    reorder_point = max(1, math.ceil(avg_daily * 2))
                    target_stock = max(2, math.ceil(avg_daily * fdc_days))
                    available_pipeline = outstanding[key]
                    if fdc_stock[key] + available_pipeline < reorder_point:
                        request_qty = target_stock - fdc_stock[key] - available_pipeline
                        if request_qty > 0:
                            transfer_requests.append((fdc_id, sku_id, request_qty))

                for sku_id, qty in demand_by_date_fdc.get((date_key, fdc_id), []):
                    if sku_id not in assortment[fdc_id]:
                        stockout_writer.writerow(
                            {
                                "date": date_key,
                                "node_id": fdc_id,
                                "node_type": "FDC",
                                "sku_id": sku_id,
                                "stockout_flag": BOOL_TRUE,
                                "stockout_qty": qty,
                                "stockout_reason": "not_assorted",
                            }
                        )
                        stockout_count += 1

            for fdc_id, sku_id, request_qty in transfer_requests:
                rdc_id = fdc_to_rdc[fdc_id]
                available = rdc_stock[(rdc_id, sku_id)]
                ship_qty = min(request_qty, available)
                if ship_qty < request_qty:
                    missing = request_qty - ship_qty
                    stockout_writer.writerow(
                        {
                            "date": date_key,
                            "node_id": rdc_id,
                            "node_type": "RDC",
                            "sku_id": sku_id,
                            "stockout_flag": BOOL_TRUE,
                            "stockout_qty": missing,
                            "stockout_reason": "insufficient_rdc_inventory",
                        }
                    )
                    stockout_count += 1
                if ship_qty <= 0:
                    continue
                rdc_stock[(rdc_id, sku_id)] -= ship_qty
                lead_time = rng.randint(lead_min, lead_max)
                arrival_date = parse_date(date_key) + timedelta(days=lead_time)
                arrival_key = date_text(arrival_date)
                outstanding[(fdc_id, sku_id)] += ship_qty
                arrivals[arrival_key][(fdc_id, sku_id)] += ship_qty
                transfer_count += 1
                transfer_writer.writerow(
                    {
                        "transfer_id": f"T{transfer_count:010d}",
                        "ship_date": date_key,
                        "arrival_date": arrival_key,
                        "rdc_id": rdc_id,
                        "fdc_id": fdc_id,
                        "sku_id": sku_id,
                        "transfer_qty": ship_qty,
                        "lead_time_days": lead_time,
                    }
                )

            for fdc_id in fdc_ids:
                for sku_id in sorted(assortment[fdc_id]):
                    snapshot_writer.writerow(
                        {
                            "date": date_key,
                            "node_id": fdc_id,
                            "node_type": "FDC",
                            "sku_id": sku_id,
                            "on_hand_qty": fdc_stock[(fdc_id, sku_id)],
                            "reserved_qty": 0,
                            "in_transit_qty": max(0, outstanding[(fdc_id, sku_id)]),
                        }
                    )
                    snapshot_count += 1
            for rdc_id in rdc_ids:
                for sku_id in skus_by_id:
                    snapshot_writer.writerow(
                        {
                            "date": date_key,
                            "node_id": rdc_id,
                            "node_type": "RDC",
                            "sku_id": sku_id,
                            "on_hand_qty": rdc_stock[(rdc_id, sku_id)],
                            "reserved_qty": 0,
                            "in_transit_qty": 0,
                        }
                    )
                    snapshot_count += 1

    cost_rows = [
        {
            "cost_item": "transfer_cost",
            "unit": "per_unit",
            "value": cost_cfg["transfer_cost_per_unit"],
            "currency": "CNY",
            "description": "RDC to FDC transfer cost.",
        },
        {
            "cost_item": "rdc_fallback_cost",
            "unit": "per_unit",
            "value": cost_cfg["rdc_fallback_cost_per_unit"],
            "currency": "CNY",
            "description": "RDC fallback fulfillment cost.",
        },
        {
            "cost_item": "lost_sales_cost",
            "unit": "per_unit",
            "value": cost_cfg["lost_sales_cost_per_unit"],
            "currency": "CNY",
            "description": "Lost sales penalty cost.",
        },
        {
            "cost_item": "holding_cost",
            "unit": "per_unit_day",
            "value": cost_cfg["holding_cost_per_unit_day"],
            "currency": "CNY",
            "description": "Inventory holding cost.",
        },
    ]
    cost_count = write_csv(cost_path, ["cost_item", "unit", "value", "currency", "description"], cost_rows)
    return snapshot_count, transfer_count, stockout_count, cost_count


def write_manifest(output_dir: Path, manifest: dict[str, Any]) -> None:
    with (output_dir / "manifest.yaml").open("w", encoding="utf-8") as f:
        yaml.safe_dump(manifest, f, sort_keys=False, allow_unicode=True)


def generate(config_path: Path, data_version: str | None) -> dict[str, Any]:
    config = read_yaml(config_path)
    seed = int(config["seed"])
    rng = random.Random(seed)
    output_dir = Path("data/synthetic") / (data_version or str(config["data_version"]))
    output_dir.mkdir(parents=True, exist_ok=True)

    skus, skus_by_id = generate_skus(config, rng)
    sku_count = write_csv(
        output_dir / "sku_master.csv",
        [
            "sku_id",
            "category_id",
            "brand_id",
            "price",
            "temperature_zone",
            "volume",
            "weight",
            "shelf_life_days",
            "is_regular_product",
            "base_popularity",
        ],
        skus,
    )

    warehouses, rdc_ids, fdc_ids, fdc_to_rdc = generate_warehouses(config, rng)
    warehouse_count = write_csv(
        output_dir / "warehouse_master.csv",
        [
            "node_id",
            "node_type",
            "rdc_id",
            "city_id",
            "region_id",
            "capacity_units",
            "support_ambient",
            "support_chilled",
            "support_frozen",
        ],
        warehouses,
    )

    eligibility_rows, eligible_by_fdc = generate_eligibility(skus, warehouses, fdc_to_rdc, rng)
    eligibility_count = write_csv(
        output_dir / "sku_fdc_eligibility.csv",
        ["sku_id", "fdc_id", "rdc_id", "eligible_flag", "ineligible_reason"],
        eligibility_rows,
    )

    calendar_rows = generate_calendar(config)
    calendar_count = write_csv(
        output_dir / "calendar.csv",
        [
            "date",
            "day_of_week",
            "is_weekend",
            "is_holiday",
            "campaign_window",
            "campaign_phase",
            "demand_multiplier",
        ],
        calendar_rows,
    )

    promotion_rows, promotion_by_date = generate_promotions(config, skus, calendar_rows, rng)
    promotion_count = write_csv(
        output_dir / "promotion_plan.csv",
        [
            "date",
            "sku_id",
            "promotion_type",
            "discount_rate",
            "coupon_value",
            "planned_exposure_level",
            "campaign_phase",
            "planned_demand_lift",
        ],
        promotion_rows,
    )

    order_count, item_count, demand, fdc_date_orders = generate_orders(
        config,
        output_dir,
        calendar_rows,
        skus_by_id,
        fdc_ids,
        fdc_to_rdc,
        eligible_by_fdc,
        promotion_by_date,
        rng,
    )

    snapshot_count, transfer_count, stockout_count, cost_count = generate_inventory_tables(
        config,
        output_dir,
        calendar_rows,
        warehouses,
        skus_by_id,
        fdc_ids,
        rdc_ids,
        fdc_to_rdc,
        eligible_by_fdc,
        demand,
        rng,
    )

    manifest = {
        "data_version": output_dir.name,
        "source_config_data_version": config["data_version"],
        "seed": seed,
        "config": str(config_path),
        "schema_version": config["schema_version"],
        "generator_version": config["generator_version"],
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "output_dir": str(output_dir),
        "counts": {
            "sku_master": sku_count,
            "warehouse_master": warehouse_count,
            "sku_fdc_eligibility": eligibility_count,
            "calendar": calendar_count,
            "promotion_plan": promotion_count,
            "orders": order_count,
            "order_items": item_count,
            "inventory_snapshot": snapshot_count,
            "transfer_plan": transfer_count,
            "stockout_events": stockout_count,
            "cost_config": cost_count,
            "fdc_date_order_cells": len(fdc_date_orders),
            "fdc_sku_date_demand_cells": len(demand),
        },
    }
    write_manifest(output_dir, manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate FAIA synthetic data.")
    parser.add_argument("--config", default="data/configs/synthetic_small.yaml", help="Path to config YAML.")
    parser.add_argument("--data-version", default="v001", help="Output data version directory name.")
    args = parser.parse_args()

    manifest = generate(Path(args.config), args.data_version)
    print(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True))


if __name__ == "__main__":
    main()
