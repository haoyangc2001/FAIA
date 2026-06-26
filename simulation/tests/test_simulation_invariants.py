"""Unit tests for simulation invariants and hard constraints."""

from __future__ import annotations

import unittest

from simulation.src.allocation import (
    AllocationRules,
    allocate_transfer_decision,
    build_transfer_event,
    calculate_arrival_date,
    validate_transfer_event,
)
from simulation.src.fulfillment import DemandRecord, fulfill_demand_record, validate_fulfillment_records
from simulation.src.policy import TransferDecision
from simulation.src.state import FulfillmentRecord, SimulationContext, SimulationState


def build_context(
    eligible_pairs: set[tuple[str, str]] | None = None,
    fdc_capacity: dict[str, int] | None = None,
) -> SimulationContext:
    return SimulationContext(
        experiment_id="unit_test",
        data_version="v_test",
        assortment_version="assortment_test",
        policy_version="policy_test",
        simulation_rule_version="rule_test",
        simulation_start_date="2026-01-01",
        simulation_end_date="2026-01-03",
        fdc_to_rdc={"FDC1": "RDC1"},
        fdc_capacity=fdc_capacity or {"FDC1": 100},
        eligible_pairs=eligible_pairs if eligible_pairs is not None else {("FDC1", "SKU1")},
    )


def build_decision(sku_id: str = "SKU1", qty: int = 5) -> TransferDecision:
    return TransferDecision(
        simulation_date="2026-01-01",
        rdc_id="RDC1",
        fdc_id="FDC1",
        sku_id=sku_id,
        recommended_transfer_qty=qty,
        policy_version="policy_test",
    )


class AllocationInvariantTests(unittest.TestCase):
    def test_lead_time_arrival_date_is_deterministic(self) -> None:
        self.assertEqual(calculate_arrival_date("2026-01-01", 2), "2026-01-03")
        event = build_transfer_event("2026-01-01", "RDC1", "FDC1", "SKU1", 3, 2)
        validate_transfer_event(event)

    def test_lead_time_mismatch_is_rejected(self) -> None:
        event = build_transfer_event("2026-01-01", "RDC1", "FDC1", "SKU1", 3, 2)
        bad_event = type(event)(
            ship_date=event.ship_date,
            arrival_date="2026-01-04",
            rdc_id=event.rdc_id,
            fdc_id=event.fdc_id,
            sku_id=event.sku_id,
            qty=event.qty,
            lead_time_days=event.lead_time_days,
        )
        with self.assertRaises(ValueError):
            validate_transfer_event(bad_event)

    def test_transfer_is_clipped_by_rdc_inventory(self) -> None:
        state = SimulationState(current_date="2026-01-01")
        state.add_rdc_inventory("RDC1", "SKU1", 4)
        result = allocate_transfer_decision(
            decision=build_decision(qty=9),
            state=state,
            context=build_context(),
            rules=AllocationRules(default_lead_time_days=2),
            transfer_id="T001",
        )
        self.assertEqual(result.actual_transfer_qty, 4)
        self.assertEqual(result.clipped_qty, 5)
        self.assertIn("rdc_inventory_limit", result.clip_reason)

    def test_unfulfillable_sku_transfer_is_cancelled(self) -> None:
        state = SimulationState(current_date="2026-01-01")
        state.add_rdc_inventory("RDC1", "SKU2", 10)
        result = allocate_transfer_decision(
            decision=build_decision(sku_id="SKU2", qty=5),
            state=state,
            context=build_context(eligible_pairs={("FDC1", "SKU1")}),
            rules=AllocationRules(default_lead_time_days=2),
            transfer_id="T002",
        )
        self.assertEqual(result.actual_transfer_qty, 0)
        self.assertEqual(result.status, "cancelled")
        self.assertIn("not_in_candidate_pool", result.clip_reason)

    def test_fdc_capacity_limit_blocks_new_sku_position(self) -> None:
        state = SimulationState(current_date="2026-01-01")
        state.add_rdc_inventory("RDC1", "SKU2", 10)
        state.add_fdc_inventory("FDC1", "SKU_EXISTING", 1)
        result = allocate_transfer_decision(
            decision=build_decision(sku_id="SKU2", qty=5),
            state=state,
            context=build_context(
                eligible_pairs={("FDC1", "SKU2")},
                fdc_capacity={"FDC1": 1},
            ),
            rules=AllocationRules(default_lead_time_days=2),
            transfer_id="T003",
        )
        self.assertEqual(result.actual_transfer_qty, 0)
        self.assertEqual(result.status, "cancelled")
        self.assertIn("fdc_capacity_limit", result.clip_reason)


class FulfillmentInvariantTests(unittest.TestCase):
    def test_fulfillment_preserves_demand_and_non_negative_inventory(self) -> None:
        state = SimulationState(current_date="2026-01-01")
        state.add_fdc_inventory("FDC1", "SKU1", 3)
        state.add_rdc_inventory("RDC1", "SKU1", 4)
        record = fulfill_demand_record(
            DemandRecord("2026-01-01", "FDC1", "SKU1", 10),
            state=state,
            context=build_context(),
        )
        self.assertEqual(record.fdc_fulfilled_qty, 3)
        self.assertEqual(record.rdc_fallback_qty, 4)
        self.assertEqual(record.lost_sales_qty, 3)
        self.assertEqual(
            record.demand_qty,
            record.fdc_fulfilled_qty + record.rdc_fallback_qty + record.lost_sales_qty,
        )
        state.validate_non_negative()

    def test_bad_fulfillment_record_is_rejected(self) -> None:
        bad_record = FulfillmentRecord(
            simulation_date="2026-01-01",
            fdc_id="FDC1",
            rdc_id="RDC1",
            sku_id="SKU1",
            demand_qty=10,
            fdc_fulfilled_qty=3,
            rdc_fallback_qty=3,
            lost_sales_qty=3,
        )
        with self.assertRaises(ValueError):
            validate_fulfillment_records([bad_record])

    def test_negative_inventory_is_rejected(self) -> None:
        state = SimulationState(current_date="2026-01-01")
        state.rdc_on_hand_inventory[("RDC1", "SKU1")] = -1
        with self.assertRaises(ValueError):
            state.validate_non_negative()


if __name__ == "__main__":
    unittest.main()
