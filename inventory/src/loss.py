"""Loss helpers for the future end-to-end inventory allocation framework."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LossWeights:
    operation: float = 1.0
    prediction: float = 0.0
    safety_stock: float = 0.0


def compute_operational_loss(metrics_summary: dict[str, Any], weights: LossWeights | None = None) -> dict[str, float]:
    """Compute a simple scalar loss from simulation metrics.

    This is intentionally small and deterministic for the first interface
    version. Future model training can replace it with differentiable or
    multi-period losses without changing the module boundary.
    """

    w = weights or LossWeights()
    total_cost = float(metrics_summary.get("total_cost", 0.0))
    loss_ratio = float(metrics_summary.get("loss_ratio", 0.0))
    operation_loss = total_cost + loss_ratio
    total_loss = w.operation * operation_loss
    return {
        "operation_loss": round(operation_loss, 8),
        "prediction_loss": 0.0,
        "safety_stock_loss": 0.0,
        "total_loss": round(total_loss, 8),
    }
