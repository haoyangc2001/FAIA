"""Unit tests for inventory state, forecast, TISS and allocation baselines."""

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

import yaml

from inventory.src.forecasting import build_demand_forecast_rows
from inventory.src.policies import generate_transfer_recommendation_rows
from inventory.scripts.run_inventory_baseline import run_inventory_baseline
from inventory.src.state_builder import build_inventory_state_rows
from inventory.src.tiss import build_tiss_rows
from inventory.src.validation import validate_inventory_run


def write_rows(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


class InventoryBaselineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.config = self.build_fixture(self.root)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def build_fixture(self, root: Path) -> dict[str, object]:
        write_rows(
            root / "warehouse_master.csv",
            ["node_id", "node_type", "rdc_id", "city_id", "region_id", "capacity_units", "support_ambient", "support_chilled", "support_frozen"],
            [
                {"node_id": "RDC1", "node_type": "RDC", "rdc_id": "", "city_id": "C1", "region_id": "R1", "capacity_units": 1000, "support_ambient": "true", "support_chilled": "true", "support_frozen": "true"},
                {"node_id": "FDC1", "node_type": "FDC", "rdc_id": "RDC1", "city_id": "C1", "region_id": "R1", "capacity_units": 100, "support_ambient": "true", "support_chilled": "true", "support_frozen": "true"},
                {"node_id": "FDC2", "node_type": "FDC", "rdc_id": "RDC1", "city_id": "C1", "region_id": "R2", "capacity_units": 100, "support_ambient": "true", "support_chilled": "true", "support_frozen": "true"},
            ],
        )
        write_rows(
            root / "sku_fdc_eligibility.csv",
            ["sku_id", "fdc_id", "rdc_id", "eligible_flag", "ineligible_reason"],
            [
                {"sku_id": "SKU1", "fdc_id": "FDC1", "rdc_id": "RDC1", "eligible_flag": "true", "ineligible_reason": ""},
                {"sku_id": "SKU1", "fdc_id": "FDC2", "rdc_id": "RDC1", "eligible_flag": "true", "ineligible_reason": ""},
                {"sku_id": "SKU2", "fdc_id": "FDC1", "rdc_id": "RDC1", "eligible_flag": "true", "ineligible_reason": ""},
            ],
        )
        write_rows(
            root / "assortment_result.csv",
            [
                "experiment_id",
                "data_version",
                "candidate_pool_version",
                "k_rule_version",
                "method_version",
                "assortment_version",
                "anchor_date",
                "effective_start_date",
                "effective_end_date",
                "fdc_id",
                "rdc_id",
                "sku_id",
                "selected_flag",
                "rank",
                "score",
                "topk_score",
                "structure_score",
                "ml_score",
                "source_tag",
                "selected_k",
                "candidate_sku_count",
                "cumulative_volume",
            ],
            [
                {"experiment_id": "a1", "data_version": "v_test", "candidate_pool_version": "c1", "k_rule_version": "k1", "method_version": "hybrid_v1", "assortment_version": "assortment_test", "anchor_date": "2026-01-05", "effective_start_date": "2026-01-06", "effective_end_date": "2026-01-08", "fdc_id": "FDC1", "rdc_id": "RDC1", "sku_id": "SKU1", "selected_flag": "true", "rank": 1, "score": 1, "topk_score": 1, "structure_score": 1, "ml_score": "", "source_tag": "hybrid", "selected_k": 2, "candidate_sku_count": 3, "cumulative_volume": 1},
                {"experiment_id": "a1", "data_version": "v_test", "candidate_pool_version": "c1", "k_rule_version": "k1", "method_version": "hybrid_v1", "assortment_version": "assortment_test", "anchor_date": "2026-01-05", "effective_start_date": "2026-01-06", "effective_end_date": "2026-01-08", "fdc_id": "FDC2", "rdc_id": "RDC1", "sku_id": "SKU1", "selected_flag": "true", "rank": 1, "score": 1, "topk_score": 1, "structure_score": 1, "ml_score": "", "source_tag": "hybrid", "selected_k": 1, "candidate_sku_count": 3, "cumulative_volume": 1},
                {"experiment_id": "a1", "data_version": "v_test", "candidate_pool_version": "c1", "k_rule_version": "k1", "method_version": "hybrid_v1", "assortment_version": "assortment_test", "anchor_date": "2026-01-05", "effective_start_date": "2026-01-06", "effective_end_date": "2026-01-08", "fdc_id": "FDC1", "rdc_id": "RDC1", "sku_id": "SKU2", "selected_flag": "true", "rank": 2, "score": 1, "topk_score": 1, "structure_score": 1, "ml_score": "", "source_tag": "hybrid", "selected_k": 2, "candidate_sku_count": 3, "cumulative_volume": 1},
            ],
        )
        write_rows(
            root / "inventory_daily_state.csv",
            ["date", "node_id", "node_type", "sku_id", "on_hand_qty", "reserved_qty", "in_transit_qty", "available_qty", "inventory_position_qty"],
            [
                {"date": "2026-01-05", "node_id": "RDC1", "node_type": "RDC", "sku_id": "SKU1", "on_hand_qty": 70, "reserved_qty": 0, "in_transit_qty": 0, "available_qty": 70, "inventory_position_qty": 70},
                {"date": "2026-01-05", "node_id": "RDC1", "node_type": "RDC", "sku_id": "SKU2", "on_hand_qty": 20, "reserved_qty": 0, "in_transit_qty": 0, "available_qty": 20, "inventory_position_qty": 20},
                {"date": "2026-01-05", "node_id": "FDC1", "node_type": "FDC", "sku_id": "SKU1", "on_hand_qty": 0, "reserved_qty": 0, "in_transit_qty": 0, "available_qty": 0, "inventory_position_qty": 0},
                {"date": "2026-01-05", "node_id": "FDC2", "node_type": "FDC", "sku_id": "SKU1", "on_hand_qty": 0, "reserved_qty": 0, "in_transit_qty": 0, "available_qty": 0, "inventory_position_qty": 0},
                {"date": "2026-01-05", "node_id": "FDC1", "node_type": "FDC", "sku_id": "SKU2", "on_hand_qty": 30, "reserved_qty": 0, "in_transit_qty": 0, "available_qty": 30, "inventory_position_qty": 30},
            ],
        )
        write_rows(
            root / "transfer_plan.csv",
            ["transfer_id", "ship_date", "arrival_date", "rdc_id", "fdc_id", "sku_id", "transfer_qty", "lead_time_days"],
            [
                {"transfer_id": "T1", "ship_date": "2026-01-04", "arrival_date": "2026-01-06", "rdc_id": "RDC1", "fdc_id": "FDC1", "sku_id": "SKU1", "transfer_qty": 2, "lead_time_days": 2},
            ],
        )
        demand_rows = []
        for date in ["2026-01-03", "2026-01-04", "2026-01-05"]:
            demand_rows.extend(
                [
                    {"date": date, "fdc_id": "FDC1", "sku_id": "SKU1", "order_count": 10, "demand_qty": 10},
                    {"date": date, "fdc_id": "FDC2", "sku_id": "SKU1", "order_count": 20, "demand_qty": 20},
                    {"date": date, "fdc_id": "FDC1", "sku_id": "SKU2", "order_count": 1, "demand_qty": 1},
                ]
            )
        demand_rows.append({"date": "2026-01-06", "fdc_id": "FDC1", "sku_id": "SKU1", "order_count": 999, "demand_qty": 999})
        write_rows(root / "fdc_sku_daily_demand.csv", ["date", "fdc_id", "sku_id", "order_count", "demand_qty"], demand_rows)
        write_rows(
            root / "calendar.csv",
            ["date", "day_of_week", "is_weekend", "is_holiday", "campaign_window", "campaign_phase", "demand_multiplier"],
            [
                {"date": "2026-01-06", "day_of_week": 2, "is_weekend": "false", "is_holiday": "false", "campaign_window": "", "campaign_phase": "", "demand_multiplier": 1.0},
                {"date": "2026-01-07", "day_of_week": 3, "is_weekend": "false", "is_holiday": "false", "campaign_window": "", "campaign_phase": "", "demand_multiplier": 1.0},
                {"date": "2026-01-08", "day_of_week": 4, "is_weekend": "false", "is_holiday": "false", "campaign_window": "", "campaign_phase": "", "demand_multiplier": 1.0},
            ],
        )
        write_rows(
            root / "promotion_plan.csv",
            ["date", "sku_id", "promotion_type", "discount_rate", "coupon_value", "planned_exposure_level", "campaign_phase", "planned_demand_lift"],
            [],
        )
        write_rows(
            root / "cost_config.csv",
            ["cost_item", "unit", "value", "currency", "description"],
            [
                {"cost_item": "transfer_cost", "unit": "per_unit", "value": 0.1, "currency": "CNY", "description": ""},
                {"cost_item": "rdc_fallback_cost", "unit": "per_unit", "value": 1.0, "currency": "CNY", "description": ""},
                {"cost_item": "lost_sales_cost", "unit": "per_unit", "value": 5.0, "currency": "CNY", "description": ""},
                {"cost_item": "holding_cost", "unit": "per_unit_day", "value": 0.01, "currency": "CNY", "description": ""},
            ],
        )
        rules = {
            "simulation_rule_version": "rule_test",
            "description": "toy simulation rule",
            "time": {
                "default_lead_time_days": 2,
                "min_lead_time_days": 1,
                "max_lead_time_days": 3,
            },
            "allocation": {
                "require_candidate_pair": True,
                "require_non_negative_transfer": True,
                "integer_transfer_qty": True,
                "clip_by_rdc_inventory": True,
                "clip_by_fdc_capacity": True,
                "rdc_reserve_qty_per_sku": 0,
                "fdc_receiving_limit_units_per_day": None,
                "rdc_shipping_limit_units_per_day": None,
            },
        }
        (root / "simulation_rule.yaml").write_text(yaml.safe_dump(rules, sort_keys=False), encoding="utf-8")
        return {
            "experiment_id": "exp_test",
            "data_version": "v_test",
            "assortment_version": "assortment_test",
            "inventory_version": "inventory_test",
            "simulation_rule_version": "rule_test",
            "decision_date": "2026-01-05",
            "effective_start_date": "2026-01-06",
            "effective_end_date": "2026-01-08",
            "initial_inventory_date": "2026-01-05",
            "inputs": {
                "warehouse_master": str(root / "warehouse_master.csv"),
                "sku_fdc_eligibility": str(root / "sku_fdc_eligibility.csv"),
                "assortment_result": str(root / "assortment_result.csv"),
                "inventory_daily_state": str(root / "inventory_daily_state.csv"),
                "transfer_plan": str(root / "transfer_plan.csv"),
                "fdc_sku_daily_demand": str(root / "fdc_sku_daily_demand.csv"),
                "calendar": str(root / "calendar.csv"),
                "promotion_plan": str(root / "promotion_plan.csv"),
                "cost_config": str(root / "cost_config.csv"),
            },
            "state": {"source_snapshot_date": "2026-01-05", "default_lead_time_days": 2, "include_rdc_nodes": True, "include_fdc_nodes": True},
            "forecast": {"method": "historical_mean", "forecast_version": "f_test", "model_version": "none", "history_window_days": 3, "horizon_days": 3, "promotion_adjustment_enabled": True, "calendar_adjustment_enabled": True},
            "tiss": {"tiss_version": "tiss_test", "model_version": "none", "service_factor": 0.0, "replenishment_window_days": 3, "min_safety_stock_qty": 0},
            "policy": {"policy_name": "base_stock", "policy_version": "p_test", "model_version": "none", "min_transfer_qty": 1, "max_transfer_qty_per_sku": 300, "use_greedy_allocation": True},
            "allocation": {"rdc_business_reserve_qty_per_sku": 0, "priority_score": {"demand_weight": 1.0, "lost_sales_cost_weight": 1.0, "promotion_weight": 1.0, "inventory_position_penalty": 1.0}},
            "rules": {"simulation_rule": str(root / "simulation_rule.yaml")},
            "simulation": {"enabled": True, "rollout_window_days": 3},
            "output": {"run_dir": str(root / "run"), "report_dir": str(root / "reports")},
        }

    def test_state_builder_uses_assortment_and_open_pipeline(self) -> None:
        state_rows = build_inventory_state_rows(self.config)
        fdc1_sku1 = next(row for row in state_rows if row["node_id"] == "FDC1" and row["sku_id"] == "SKU1")
        self.assertEqual(fdc1_sku1["in_transit_qty"], 2)
        self.assertEqual(fdc1_sku1["inventory_position_qty"], 2)
        self.assertEqual(fdc1_sku1["assortment_mask"], "true")
        rdc_sku1 = next(row for row in state_rows if row["node_id"] == "RDC1" and row["sku_id"] == "SKU1")
        self.assertEqual(rdc_sku1["rdc_allocatable_qty"], 70)

    def test_forecast_uses_only_history_not_future_demand(self) -> None:
        state_rows = build_inventory_state_rows(self.config)
        forecast_rows = build_demand_forecast_rows(self.config, state_rows)
        fdc1_sku1 = [
            row
            for row in forecast_rows
            if row["node_type"] == "FDC" and row["fdc_id"] == "FDC1" and row["sku_id"] == "SKU1"
        ]
        self.assertEqual(len(fdc1_sku1), 3)
        self.assertEqual(fdc1_sku1[0]["feature_window_end_date"], "2026-01-05")
        self.assertEqual(fdc1_sku1[0]["forecast_qty"], 10.0)

    def test_tiss_projection_and_base_stock_greedy_allocation(self) -> None:
        state_rows = build_inventory_state_rows(self.config)
        forecast_rows = build_demand_forecast_rows(self.config, state_rows)
        tiss_rows = build_tiss_rows(self.config, state_rows, forecast_rows)
        transfers = generate_transfer_recommendation_rows(self.config, state_rows, tiss_rows)
        by_key = {(row["fdc_id"], row["sku_id"]): row for row in transfers}

        self.assertNotIn(("FDC1", "SKU2"), by_key)
        self.assertEqual(by_key[("FDC1", "SKU1")]["recommended_transfer_qty"], 48)
        self.assertEqual(by_key[("FDC1", "SKU1")]["actual_transfer_qty"], 0)
        self.assertEqual(by_key[("FDC2", "SKU1")]["recommended_transfer_qty"], 100)
        self.assertEqual(by_key[("FDC2", "SKU1")]["actual_transfer_qty"], 10)
        self.assertGreater(by_key[("FDC2", "SKU1")]["priority_score"], by_key[("FDC1", "SKU1")]["priority_score"])
        self.assertEqual(by_key[("FDC2", "SKU1")]["arrival_date"], "2026-01-08")

    def test_tiss_zeroes_unselected_or_ineligible_fdc_rows(self) -> None:
        state_rows = build_inventory_state_rows(self.config)
        extra_row = dict(next(row for row in state_rows if row["node_id"] == "FDC1" and row["sku_id"] == "SKU1"))
        extra_row["sku_id"] = "SKU_X"
        extra_row["assortment_mask"] = "false"
        extra_row["eligible_mask"] = "false"
        rows = build_tiss_rows(self.config, state_rows + [extra_row], [])
        projected = next(row for row in rows if row["node_id"] == "FDC1" and row["sku_id"] == "SKU_X")
        self.assertEqual(projected["safety_stock_qty"], 0)
        self.assertEqual(projected["target_inventory_qty"], 0)

    def test_run_inventory_baseline_writes_manifest_validation_and_simulation_metrics(self) -> None:
        config_path = self.root / "inventory_config.yaml"
        config_path.write_text(yaml.safe_dump(self.config, sort_keys=False), encoding="utf-8")
        summary = run_inventory_baseline(config_path)
        run_dir = self.root / "run"
        manifest_path = run_dir / "inventory_manifest.yaml"
        validation_path = run_dir / "inventory_validation_summary.json"
        metrics_path = run_dir / "simulation_metrics.json"

        self.assertEqual(summary["simulation_status"], "completed")
        self.assertEqual(summary["validation_status"], "PASS")
        self.assertTrue(manifest_path.exists())
        self.assertTrue(validation_path.exists())
        self.assertTrue(metrics_path.exists())

        validation = validate_inventory_run(manifest_path, write_outputs=False, update_manifest=False)
        self.assertTrue(validation["passed"])


if __name__ == "__main__":
    unittest.main()
