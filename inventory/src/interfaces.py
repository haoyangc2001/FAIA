"""End-to-end inventory allocation interface definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class InventoryBatch:
    """A typed payload passed between inventory allocation modules."""

    config: dict[str, Any]
    inventory_state_rows: list[dict[str, Any]]
    demand_forecast_rows: list[dict[str, Any]]
    tiss_rows: list[dict[str, Any]]
    transfer_recommendation_rows: list[dict[str, Any]]


class ForecastingModule(Protocol):
    forecast_version: str
    model_version: str

    def predict(self, config: dict[str, Any], inventory_state_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return demand_forecast rows."""


class TISSGenerationModule(Protocol):
    tiss_version: str
    model_version: str

    def generate(
        self,
        config: dict[str, Any],
        inventory_state_rows: list[dict[str, Any]],
        demand_forecast_rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Return tiss_result rows."""


class SimulationModule(Protocol):
    simulation_rule_version: str

    def evaluate(self, config: dict[str, Any], transfer_recommendation_rows: list[dict[str, Any]]) -> dict[str, Any]:
        """Return simulation metrics and output metadata."""


class LossComputer(Protocol):
    loss_version: str

    def compute(self, batch: InventoryBatch, simulation_metrics: dict[str, Any]) -> dict[str, float]:
        """Return prediction, operations and constraint losses."""
