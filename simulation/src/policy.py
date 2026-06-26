"""Policy interfaces and baseline policies for FAIA simulation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Protocol

import yaml

from simulation.src.state import SimulationContext, SimulationState


DemandHistory = dict[tuple[str, str], float]


@dataclass(frozen=True)
class TransferDecision:
    """A policy recommendation before hard-constraint clipping."""

    simulation_date: str
    rdc_id: str
    fdc_id: str
    sku_id: str
    recommended_transfer_qty: int
    policy_version: str
    target_inventory_qty: int | None = None
    safety_stock_qty: int | None = None
    lead_time_days: int | None = None
    reason: str = ""


class TransferPolicy(Protocol):
    policy_version: str

    def generate_decisions(
        self,
        simulation_date: str,
        state: SimulationState,
        context: SimulationContext,
        demand_history: DemandHistory | None = None,
    ) -> list[TransferDecision]:
        """Generate transfer decisions for one simulation date."""


@dataclass
class NoTransferPolicy:
    """Baseline policy that generates no transfer recommendations."""

    policy_version: str = "no_transfer_v001"

    def generate_decisions(
        self,
        simulation_date: str,
        state: SimulationState,
        context: SimulationContext,
        demand_history: DemandHistory | None = None,
    ) -> list[TransferDecision]:
        return []


@dataclass
class HistoricalMeanPolicy:
    """Recommend replenishment based on historical average demand."""

    policy_version: str = "historical_mean_v001"
    cover_days: int = 3
    min_transfer_qty: int = 1
    max_transfer_qty_per_sku: int = 200

    def generate_decisions(
        self,
        simulation_date: str,
        state: SimulationState,
        context: SimulationContext,
        demand_history: DemandHistory | None = None,
    ) -> list[TransferDecision]:
        if not demand_history:
            return []
        decisions: list[TransferDecision] = []
        for fdc_id, sku_id in sorted(context.eligible_pairs):
            avg_daily_demand = demand_history.get((fdc_id, sku_id), 0.0)
            if avg_daily_demand <= 0:
                continue
            target_qty = round(avg_daily_demand * self.cover_days)
            current_position = state.get_fdc_inventory_position(fdc_id, sku_id)
            recommended = max(0, target_qty - current_position)
            recommended = min(recommended, self.max_transfer_qty_per_sku)
            if recommended >= self.min_transfer_qty:
                decisions.append(
                    TransferDecision(
                        simulation_date=simulation_date,
                        rdc_id=context.fdc_to_rdc[fdc_id],
                        fdc_id=fdc_id,
                        sku_id=sku_id,
                        recommended_transfer_qty=recommended,
                        policy_version=self.policy_version,
                        target_inventory_qty=target_qty,
                        reason="historical_mean_gap",
                    )
                )
        return decisions


@dataclass
class BaseStockPolicy:
    """Recommend replenishment up to target inventory with safety stock."""

    policy_version: str = "base_stock_v001"
    target_cover_days: int = 5
    safety_cover_days: int = 2
    min_transfer_qty: int = 1
    max_transfer_qty_per_sku: int = 300

    def generate_decisions(
        self,
        simulation_date: str,
        state: SimulationState,
        context: SimulationContext,
        demand_history: DemandHistory | None = None,
    ) -> list[TransferDecision]:
        if not demand_history:
            return []
        decisions: list[TransferDecision] = []
        for fdc_id, sku_id in sorted(context.eligible_pairs):
            avg_daily_demand = demand_history.get((fdc_id, sku_id), 0.0)
            if avg_daily_demand <= 0:
                continue
            safety_stock = round(avg_daily_demand * self.safety_cover_days)
            target_inventory = round(avg_daily_demand * self.target_cover_days) + safety_stock
            current_position = state.get_fdc_inventory_position(fdc_id, sku_id)
            recommended = max(0, target_inventory - current_position)
            recommended = min(recommended, self.max_transfer_qty_per_sku)
            if recommended >= self.min_transfer_qty:
                decisions.append(
                    TransferDecision(
                        simulation_date=simulation_date,
                        rdc_id=context.fdc_to_rdc[fdc_id],
                        fdc_id=fdc_id,
                        sku_id=sku_id,
                        recommended_transfer_qty=recommended,
                        policy_version=self.policy_version,
                        target_inventory_qty=target_inventory,
                        safety_stock_qty=safety_stock,
                        reason="base_stock_gap",
                    )
                )
        return decisions


def read_policy_config(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_policy(path: Path) -> TransferPolicy:
    config = read_policy_config(path)
    policy_type = str(config["policy_type"])
    policy_version = str(config["policy_version"])
    parameters = config.get("parameters", {}) or {}
    if policy_type == "no_transfer":
        return NoTransferPolicy(policy_version=policy_version)
    if policy_type == "historical_mean":
        return HistoricalMeanPolicy(
            policy_version=policy_version,
            cover_days=int(parameters.get("cover_days", 3)),
            min_transfer_qty=int(parameters.get("min_transfer_qty", 1)),
            max_transfer_qty_per_sku=int(parameters.get("max_transfer_qty_per_sku", 200)),
        )
    if policy_type == "base_stock":
        return BaseStockPolicy(
            policy_version=policy_version,
            target_cover_days=int(parameters.get("target_cover_days", 5)),
            safety_cover_days=int(parameters.get("safety_cover_days", 2)),
            min_transfer_qty=int(parameters.get("min_transfer_qty", 1)),
            max_transfer_qty_per_sku=int(parameters.get("max_transfer_qty_per_sku", 300)),
        )
    raise ValueError(f"Unsupported policy_type: {policy_type}")


def load_average_demand(rows: Iterable[dict[str, str]], denominator_days: int) -> DemandHistory:
    """Build average daily demand by FDC-SKU from fdc_sku_daily_demand rows."""

    if denominator_days <= 0:
        raise ValueError("denominator_days must be positive")
    totals: dict[tuple[str, str], int] = {}
    for row in rows:
        key = (row["fdc_id"], row["sku_id"])
        totals[key] = totals.get(key, 0) + int(row["demand_qty"])
    return {key: qty / denominator_days for key, qty in totals.items()}

