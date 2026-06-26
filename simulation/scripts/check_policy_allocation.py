#!/usr/bin/env python3
"""Smoke-check policy loading and transfer allocation clipping."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from simulation.src.allocation import (
    allocate_transfer_decision,
    apply_transfer_allocation,
    rules_from_config,
)
from simulation.src.initialization import initialize_simulation
from simulation.src.policy import TransferDecision, load_policy


def pick_available_pair(init) -> tuple[str, str, str, int]:
    for fdc_id, sku_id in sorted(init.context.eligible_pairs):
        rdc_id = init.context.fdc_to_rdc[fdc_id]
        stock = init.state.get_rdc_on_hand(rdc_id, sku_id)
        if stock > 0:
            return rdc_id, fdc_id, sku_id, stock
    raise RuntimeError("no candidate pair with positive RDC stock found")


def main() -> None:
    parser = argparse.ArgumentParser(description="Check FAIA policy and allocation behavior.")
    parser.add_argument("--config", default="simulation/configs/simulation_small.yaml")
    args = parser.parse_args()

    init = initialize_simulation(Path(args.config))
    policy = load_policy(Path(init.config["policy"]["path"]))
    decisions = policy.generate_decisions(
        init.context.simulation_start_date,
        init.state,
        init.context,
    )
    rules = rules_from_config(init.rules)

    rdc_id, fdc_id, sku_id, rdc_stock = pick_available_pair(init)
    manual_decision = TransferDecision(
        simulation_date=init.context.simulation_start_date,
        rdc_id=rdc_id,
        fdc_id=fdc_id,
        sku_id=sku_id,
        recommended_transfer_qty=rdc_stock + 5,
        policy_version=init.context.policy_version,
        reason="manual_clip_check",
    )
    allocation = allocate_transfer_decision(
        decision=manual_decision,
        state=init.state,
        context=init.context,
        rules=rules,
        transfer_id="SIMT_CHECK_0001",
    )
    before_rdc = init.state.get_rdc_on_hand(rdc_id, sku_id)
    applied_qty = apply_transfer_allocation(init.state, allocation)
    after_rdc = init.state.get_rdc_on_hand(rdc_id, sku_id)

    invalid_decision = TransferDecision(
        simulation_date=init.context.simulation_start_date,
        rdc_id=rdc_id,
        fdc_id=fdc_id,
        sku_id="SKU_NOT_IN_POOL",
        recommended_transfer_qty=10,
        policy_version=init.context.policy_version,
        reason="manual_invalid_pair_check",
    )
    invalid_allocation = allocate_transfer_decision(
        decision=invalid_decision,
        state=init.state,
        context=init.context,
        rules=rules,
        transfer_id="SIMT_CHECK_0002",
    )

    print(
        json.dumps(
            {
                "policy_version": policy.policy_version,
                "policy_decision_count": len(decisions),
                "manual_pair": {
                    "rdc_id": rdc_id,
                    "fdc_id": fdc_id,
                    "sku_id": sku_id,
                    "rdc_stock_before": before_rdc,
                    "recommended_transfer_qty": manual_decision.recommended_transfer_qty,
                    "actual_transfer_qty": allocation.actual_transfer_qty,
                    "clipped_qty": allocation.clipped_qty,
                    "clip_reason": allocation.clip_reason,
                    "arrival_date": allocation.arrival_date,
                    "applied_qty": applied_qty,
                    "rdc_stock_after": after_rdc,
                },
                "invalid_pair": {
                    "actual_transfer_qty": invalid_allocation.actual_transfer_qty,
                    "clip_reason": invalid_allocation.clip_reason,
                    "status": invalid_allocation.status,
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

