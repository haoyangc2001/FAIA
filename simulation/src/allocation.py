"""Lead-time and transfer pipeline utilities for the FAIA simulator."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from simulation.src.policy import TransferDecision
from simulation.src.state import SimulationContext, SimulationState, TransferEvent


@dataclass(frozen=True)
class AllocationRules:
    """Hard constraints applied to policy recommendations."""

    default_lead_time_days: int = 2
    min_lead_time_days: int = 1
    max_lead_time_days: int = 3
    require_candidate_pair: bool = True
    require_non_negative_transfer: bool = True
    integer_transfer_qty: bool = True
    clip_by_rdc_inventory: bool = True
    clip_by_fdc_capacity: bool = True
    rdc_reserve_qty_per_sku: int = 0
    fdc_receiving_limit_units_per_day: int | None = None
    rdc_shipping_limit_units_per_day: int | None = None


@dataclass(frozen=True)
class TransferAllocationResult:
    """Executable transfer result after hard-constraint clipping."""

    simulation_date: str
    transfer_id: str
    rdc_id: str
    fdc_id: str
    sku_id: str
    recommended_transfer_qty: int
    actual_transfer_qty: int
    clipped_qty: int
    clip_reason: str
    ship_date: str
    arrival_date: str
    lead_time_days: int
    status: str

    def to_transfer_event(self) -> TransferEvent:
        return TransferEvent(
            ship_date=self.ship_date,
            arrival_date=self.arrival_date,
            rdc_id=self.rdc_id,
            fdc_id=self.fdc_id,
            sku_id=self.sku_id,
            qty=self.actual_transfer_qty,
            lead_time_days=self.lead_time_days,
        )

    def to_result_row(
        self,
        context: SimulationContext,
    ) -> dict[str, object]:
        return {
            "experiment_id": context.experiment_id,
            "data_version": context.data_version,
            "policy_version": context.policy_version,
            "simulation_rule_version": context.simulation_rule_version,
            "simulation_date": self.simulation_date,
            "transfer_id": self.transfer_id,
            "rdc_id": self.rdc_id,
            "fdc_id": self.fdc_id,
            "sku_id": self.sku_id,
            "recommended_transfer_qty": self.recommended_transfer_qty,
            "actual_transfer_qty": self.actual_transfer_qty,
            "clipped_qty": self.clipped_qty,
            "clip_reason": self.clip_reason,
            "ship_date": self.ship_date,
            "arrival_date": self.arrival_date,
            "lead_time_days": self.lead_time_days,
            "status": self.status,
        }


def rules_from_config(config: dict[str, Any]) -> AllocationRules:
    """Build AllocationRules from simulation_rule_v*.yaml content."""

    time_cfg = config.get("time", {})
    allocation_cfg = config.get("allocation", {})
    return AllocationRules(
        default_lead_time_days=int(time_cfg.get("default_lead_time_days", 2)),
        min_lead_time_days=int(time_cfg.get("min_lead_time_days", 1)),
        max_lead_time_days=int(time_cfg.get("max_lead_time_days", 3)),
        require_candidate_pair=bool(allocation_cfg.get("require_candidate_pair", True)),
        require_non_negative_transfer=bool(allocation_cfg.get("require_non_negative_transfer", True)),
        integer_transfer_qty=bool(allocation_cfg.get("integer_transfer_qty", True)),
        clip_by_rdc_inventory=bool(allocation_cfg.get("clip_by_rdc_inventory", True)),
        clip_by_fdc_capacity=bool(allocation_cfg.get("clip_by_fdc_capacity", True)),
        rdc_reserve_qty_per_sku=int(allocation_cfg.get("rdc_reserve_qty_per_sku", 0)),
        fdc_receiving_limit_units_per_day=allocation_cfg.get("fdc_receiving_limit_units_per_day"),
        rdc_shipping_limit_units_per_day=allocation_cfg.get("rdc_shipping_limit_units_per_day"),
    )


def parse_date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d")


def date_text(value: datetime) -> str:
    return value.strftime("%Y-%m-%d")


def calculate_arrival_date(ship_date: str, lead_time_days: int) -> str:
    """Return arrival date text from ship date and integer lead time."""

    if lead_time_days < 0:
        raise ValueError("lead_time_days must be non-negative")
    return date_text(parse_date(ship_date) + timedelta(days=lead_time_days))


def build_transfer_event(
    ship_date: str,
    rdc_id: str,
    fdc_id: str,
    sku_id: str,
    qty: int,
    lead_time_days: int,
) -> TransferEvent:
    """Create a TransferEvent using lead time to derive arrival date."""

    if qty < 0:
        raise ValueError("transfer qty must be non-negative")
    return TransferEvent(
        ship_date=ship_date,
        arrival_date=calculate_arrival_date(ship_date, lead_time_days),
        rdc_id=rdc_id,
        fdc_id=fdc_id,
        sku_id=sku_id,
        qty=qty,
        lead_time_days=lead_time_days,
    )


def enqueue_transfer(state: SimulationState, event: TransferEvent, consume_rdc_inventory: bool = True) -> int:
    """Put a transfer into pipeline and optionally consume RDC stock.

    Returns the quantity actually enqueued. If consume_rdc_inventory is true,
    the enqueued quantity is clipped by current RDC on-hand inventory.
    """

    if event.qty <= 0:
        return 0
    actual_qty = event.qty
    if consume_rdc_inventory:
        actual_qty = state.consume_rdc_inventory(event.rdc_id, event.sku_id, event.qty)
    if actual_qty <= 0:
        return 0
    state.add_pipeline_transfer(
        TransferEvent(
            ship_date=event.ship_date,
            arrival_date=event.arrival_date,
            rdc_id=event.rdc_id,
            fdc_id=event.fdc_id,
            sku_id=event.sku_id,
            qty=actual_qty,
            lead_time_days=event.lead_time_days,
        )
    )
    return actual_qty


def apply_arrivals(state: SimulationState, simulation_date: str) -> list[TransferEvent]:
    """Move all transfers arriving on simulation_date into FDC on-hand inventory."""

    arrivals = state.pop_arrivals(simulation_date)
    state.validate_non_negative()
    return arrivals


def validate_transfer_event(event: TransferEvent) -> None:
    """Validate lead-time consistency for one transfer event."""

    if event.qty < 0:
        raise ValueError("transfer qty must be non-negative")
    expected_arrival = calculate_arrival_date(event.ship_date, event.lead_time_days)
    if event.arrival_date != expected_arrival:
        raise ValueError(
            f"arrival_date mismatch: expected {expected_arrival}, got {event.arrival_date}"
        )


def allocate_transfer_decision(
    decision: TransferDecision,
    state: SimulationState,
    context: SimulationContext,
    rules: AllocationRules,
    transfer_id: str,
) -> TransferAllocationResult:
    """Clip one policy decision into an executable transfer result."""

    recommended = decision.recommended_transfer_qty
    clip_reasons: list[str] = []
    if rules.integer_transfer_qty:
        recommended = int(recommended)
    if rules.require_non_negative_transfer and recommended < 0:
        recommended = 0
        clip_reasons.append("negative_recommendation")

    lead_time_days = decision.lead_time_days if decision.lead_time_days is not None else rules.default_lead_time_days
    lead_time_days = max(rules.min_lead_time_days, min(rules.max_lead_time_days, int(lead_time_days)))
    arrival_date = calculate_arrival_date(decision.simulation_date, lead_time_days)

    actual = max(0, recommended)
    if context.fdc_to_rdc.get(decision.fdc_id) != decision.rdc_id:
        actual = 0
        clip_reasons.append("invalid_rdc_fdc_relation")

    if rules.require_candidate_pair and (decision.fdc_id, decision.sku_id) not in context.eligible_pairs:
        actual = 0
        clip_reasons.append("not_in_candidate_pool")

    if rules.clip_by_rdc_inventory:
        rdc_available = max(
            0,
            state.get_rdc_on_hand(decision.rdc_id, decision.sku_id) - rules.rdc_reserve_qty_per_sku,
        )
        if actual > rdc_available:
            actual = rdc_available
            clip_reasons.append("rdc_inventory_limit")

    if rules.clip_by_fdc_capacity and not state.fdc_has_sku_position(decision.fdc_id, decision.sku_id):
        active_skus = state.fdc_active_sku_count(decision.fdc_id)
        capacity = context.fdc_capacity.get(decision.fdc_id)
        if capacity is not None and active_skus >= capacity:
            actual = 0
            clip_reasons.append("fdc_capacity_limit")

    if rules.fdc_receiving_limit_units_per_day is not None and actual > rules.fdc_receiving_limit_units_per_day:
        actual = int(rules.fdc_receiving_limit_units_per_day)
        clip_reasons.append("fdc_receiving_limit")

    if rules.rdc_shipping_limit_units_per_day is not None and actual > rules.rdc_shipping_limit_units_per_day:
        actual = int(rules.rdc_shipping_limit_units_per_day)
        clip_reasons.append("rdc_shipping_limit")

    actual = max(0, min(actual, recommended))
    clipped = max(0, recommended - actual)
    if recommended == 0:
        status = "cancelled"
        clip_reason = ";".join(clip_reasons) or "zero_recommendation"
    elif actual == 0:
        status = "cancelled"
        clip_reason = ";".join(clip_reasons) or "fully_clipped"
    elif clipped > 0:
        status = "clipped"
        clip_reason = ";".join(dict.fromkeys(clip_reasons)) or "partially_clipped"
    else:
        status = "planned"
        clip_reason = ""

    return TransferAllocationResult(
        simulation_date=decision.simulation_date,
        transfer_id=transfer_id,
        rdc_id=decision.rdc_id,
        fdc_id=decision.fdc_id,
        sku_id=decision.sku_id,
        recommended_transfer_qty=recommended,
        actual_transfer_qty=actual,
        clipped_qty=clipped,
        clip_reason=clip_reason,
        ship_date=decision.simulation_date,
        arrival_date=arrival_date,
        lead_time_days=lead_time_days,
        status=status,
    )


def allocate_transfer_decisions(
    decisions: list[TransferDecision],
    state: SimulationState,
    context: SimulationContext,
    rules: AllocationRules,
    transfer_id_prefix: str = "SIMT",
) -> list[TransferAllocationResult]:
    results = []
    for index, decision in enumerate(decisions, start=1):
        results.append(
            allocate_transfer_decision(
                decision=decision,
                state=state,
                context=context,
                rules=rules,
                transfer_id=f"{transfer_id_prefix}{index:010d}",
            )
        )
    return results


def apply_transfer_allocation(state: SimulationState, result: TransferAllocationResult) -> int:
    """Consume RDC stock and write the allocated transfer into pipeline."""

    if result.actual_transfer_qty <= 0:
        return 0
    event = result.to_transfer_event()
    validate_transfer_event(event)
    consumed = state.consume_rdc_inventory(event.rdc_id, event.sku_id, event.qty)
    if consumed != event.qty:
        raise ValueError(
            f"RDC inventory changed after allocation: expected {event.qty}, consumed {consumed}"
        )
    state.add_pipeline_transfer(event)
    state.validate_non_negative()
    return consumed
