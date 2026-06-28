"""Tests for ML-Top-K and assortment evaluation."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from assortment.src.candidate_pool import CANDIDATE_POOL_FIELDS
from assortment.src.evaluation import evaluate_assortment
from assortment.src.k_selector import K_TABLE_FIELDS
from assortment.src.ml_topk import build_ml_topk_result
from assortment.src.publish import publish_assortment_result
from assortment.src.topk import TOPK_RESULT_FIELDS
from assortment.src.validation import validate_assortment_run


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def candidate_row(sku_id: str, historical_orders: int, volume: float = 1.0) -> dict[str, object]:
    return {
        "experiment_id": "exp_test",
        "data_version": "v_test",
        "candidate_pool_version": "candidate_pool_test",
        "anchor_date": "2026-01-01",
        "effective_start_date": "2026-01-02",
        "effective_end_date": "2026-01-03",
        "fdc_id": "FDC1",
        "rdc_id": "RDC1",
        "sku_id": sku_id,
        "eligible_flag": "true",
        "candidate_flag": "true",
        "filter_reason": "",
        "recall_source": "historical_demand",
        "category_id": "CAT1",
        "brand_id": "BR1",
        "temperature_zone": "ambient",
        "price": "10.0",
        "volume": volume,
        "weight": "1.0",
        "is_regular_product": "true",
        "historical_demand_qty": historical_orders,
        "historical_order_count": historical_orders,
        "active_demand_days": 1,
        "planned_promo_flag": "false",
        "future_promo_score": "0",
        "static_priority_score": "0.1",
    }


class MlTopKTests(unittest.TestCase):
    def test_ml_topk_scores_and_selects_top_k(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run_dir = root / "run"
            feature_path = root / "fdc_sku_features.csv"
            write_csv(
                run_dir / "candidate_pool.csv",
                CANDIDATE_POOL_FIELDS,
                [
                    candidate_row("SKU_A", 10),
                    candidate_row("SKU_B", 20),
                    candidate_row("SKU_C", 5),
                ],
            )
            write_csv(
                run_dir / "k_table.csv",
                K_TABLE_FIELDS,
                [
                    {
                        "experiment_id": "exp_test",
                        "data_version": "v_test",
                        "candidate_pool_version": "candidate_pool_test",
                        "k_rule_version": "k_rule_test",
                        "anchor_date": "2026-01-01",
                        "effective_start_date": "2026-01-02",
                        "effective_end_date": "2026-01-03",
                        "fdc_id": "FDC1",
                        "rdc_id": "RDC1",
                        "candidate_sku_count": 3,
                        "target_order_coverage": 0.8,
                        "capacity_volume_limit": 3,
                        "avg_selected_sku_volume": 1,
                        "physical_capacity_k": 2,
                        "coverage_target_k": 2,
                        "min_k": 1,
                        "max_k": 2,
                        "selected_k": 2,
                        "k_source": "coverage",
                        "historical_window_start": "2025-12-01",
                        "historical_window_end": "2026-01-01",
                    }
                ],
            )
            write_csv(
                feature_path,
                [
                    "anchor_date",
                    "fdc_id",
                    "sku_id",
                    "hist_7d_orders",
                    "hist_14d_orders",
                    "hist_30d_orders",
                    "hist_60d_orders",
                    "future_promo_days_14d",
                    "future_campaign_days_14d",
                    "base_popularity",
                ],
                [
                    {
                        "anchor_date": "2026-01-01",
                        "fdc_id": "FDC1",
                        "sku_id": "SKU_A",
                        "hist_7d_orders": 10,
                        "hist_14d_orders": 10,
                        "hist_30d_orders": 10,
                        "hist_60d_orders": 10,
                        "future_promo_days_14d": 0,
                        "future_campaign_days_14d": 0,
                        "base_popularity": 0.1,
                    },
                    {
                        "anchor_date": "2026-01-01",
                        "fdc_id": "FDC1",
                        "sku_id": "SKU_B",
                        "hist_7d_orders": 20,
                        "hist_14d_orders": 20,
                        "hist_30d_orders": 20,
                        "hist_60d_orders": 20,
                        "future_promo_days_14d": 0,
                        "future_campaign_days_14d": 0,
                        "base_popularity": 0.1,
                    },
                    {
                        "anchor_date": "2026-01-01",
                        "fdc_id": "FDC1",
                        "sku_id": "SKU_C",
                        "hist_7d_orders": 1,
                        "hist_14d_orders": 1,
                        "hist_30d_orders": 1,
                        "hist_60d_orders": 1,
                        "future_promo_days_14d": 10,
                        "future_campaign_days_14d": 0,
                        "base_popularity": 0.1,
                    },
                ],
            )
            config = {
                "experiment_id": "exp_test",
                "data_version": "v_test",
                "candidate_pool_version": "candidate_pool_test",
                "k_rule_version": "k_rule_test",
                "anchor_date": "2026-01-01",
                "effective_start_date": "2026-01-02",
                "effective_end_date": "2026-01-03",
                "inputs": {"ml_topk_features": str(feature_path)},
            }

            summary = build_ml_topk_result(config, run_dir)
            rows = read_csv(run_dir / "ml_topk_result.csv")

            self.assertEqual(summary["row_count"], 2)
            self.assertEqual([row["sku_id"] for row in rows], ["SKU_C", "SKU_B"])
            self.assertTrue((run_dir / "ml_topk_model_manifest.yaml").exists())


class EvaluationTests(unittest.TestCase):
    def test_evaluation_filters_non_regular_and_computes_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run_dir = root / "run"
            input_dir = root / "input"
            write_csv(
                run_dir / "candidate_pool.csv",
                CANDIDATE_POOL_FIELDS,
                [
                    candidate_row("SKU_A", 10),
                    candidate_row("SKU_B", 10),
                    candidate_row("SKU_C", 10),
                ],
            )
            write_csv(
                run_dir / "topk_result.csv",
                TOPK_RESULT_FIELDS,
                [
                    {
                        "experiment_id": "exp_eval",
                        "data_version": "v_test",
                        "candidate_pool_version": "candidate_pool_test",
                        "k_rule_version": "k_rule_test",
                        "method_version": "topk_test",
                        "assortment_version": "assortment_topk_test",
                        "anchor_date": "2026-01-01",
                        "effective_start_date": "2026-01-02",
                        "effective_end_date": "2026-01-03",
                        "fdc_id": "FDC1",
                        "rdc_id": "RDC1",
                        "sku_id": "SKU_A",
                        "selected_flag": "true",
                        "rank": 1,
                        "score": 10,
                        "topk_score": 10,
                        "structure_score": "",
                        "ml_score": "",
                        "source_tag": "topk",
                        "selected_k": 2,
                        "candidate_sku_count": 3,
                        "cumulative_volume": 1,
                    },
                    {
                        "experiment_id": "exp_eval",
                        "data_version": "v_test",
                        "candidate_pool_version": "candidate_pool_test",
                        "k_rule_version": "k_rule_test",
                        "method_version": "topk_test",
                        "assortment_version": "assortment_topk_test",
                        "anchor_date": "2026-01-01",
                        "effective_start_date": "2026-01-02",
                        "effective_end_date": "2026-01-03",
                        "fdc_id": "FDC1",
                        "rdc_id": "RDC1",
                        "sku_id": "SKU_B",
                        "selected_flag": "true",
                        "rank": 2,
                        "score": 9,
                        "topk_score": 9,
                        "structure_score": "",
                        "ml_score": "",
                        "source_tag": "topk",
                        "selected_k": 2,
                        "candidate_sku_count": 3,
                        "cumulative_volume": 2,
                    },
                ],
            )
            write_csv(
                input_dir / "sku_master.csv",
                ["sku_id", "category_id", "is_regular_product"],
                [
                    {"sku_id": "SKU_A", "category_id": "CAT1", "is_regular_product": "true"},
                    {"sku_id": "SKU_B", "category_id": "CAT1", "is_regular_product": "true"},
                    {"sku_id": "SKU_C", "category_id": "CAT1", "is_regular_product": "true"},
                    {"sku_id": "SKU_D", "category_id": "CAT2", "is_regular_product": "false"},
                ],
            )
            write_csv(
                input_dir / "orders.csv",
                ["order_id", "order_date", "fdc_id"],
                [
                    {"order_id": "O1", "order_date": "2026-01-02", "fdc_id": "FDC1"},
                    {"order_id": "O2", "order_date": "2026-01-02", "fdc_id": "FDC1"},
                    {"order_id": "O3", "order_date": "2026-01-02", "fdc_id": "FDC1"},
                ],
            )
            write_csv(
                input_dir / "order_items.csv",
                ["order_id", "sku_id"],
                [
                    {"order_id": "O1", "sku_id": "SKU_A"},
                    {"order_id": "O1", "sku_id": "SKU_B"},
                    {"order_id": "O2", "sku_id": "SKU_A"},
                    {"order_id": "O2", "sku_id": "SKU_C"},
                    {"order_id": "O3", "sku_id": "SKU_D"},
                ],
            )
            config = {
                "experiment_id": "exp_eval",
                "data_version": "v_test",
                "candidate_pool_version": "candidate_pool_test",
                "k_rule_version": "k_rule_test",
                "anchor_date": "2026-01-01",
                "effective_start_date": "2026-01-02",
                "effective_end_date": "2026-01-03",
                "inputs": {
                    "sku_master": str(input_dir / "sku_master.csv"),
                    "orders": str(input_dir / "orders.csv"),
                    "order_items": str(input_dir / "order_items.csv"),
                },
                "evaluation": {
                    "evaluation_split": "test",
                    "evaluation_start_date": "2026-01-02",
                    "evaluation_end_date": "2026-01-03",
                    "methods": ["topk"],
                    "report_dir": str(root / "reports"),
                },
            }

            summary = evaluate_assortment(config, run_dir)
            overall = summary["methods"]["topk"]["overall"]

            self.assertEqual(summary["regular_order_count"], 2)
            self.assertEqual(overall["regular_order_count"], 2)
            self.assertEqual(overall["covered_regular_order_count"], 1)
            self.assertEqual(overall["local_order_fulfillment_rate"], 0.5)
            self.assertEqual(overall["sku_frequency_recall_at_k"], 0.75)
            self.assertEqual(overall["candidate_hit_rate"], 1.0)
            self.assertTrue((run_dir / "assortment_metrics.json").exists())
            self.assertTrue(Path(summary["outputs"]["assortment_report"]).exists())
            payload = json.loads((run_dir / "assortment_metrics.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["comparison"][0]["method"], "topk")


def result_row(sku_id: str, rank: int, source_tag: str = "hybrid") -> dict[str, object]:
    return {
        "experiment_id": "exp_publish",
        "data_version": "v_test",
        "candidate_pool_version": "candidate_pool_test",
        "k_rule_version": "k_rule_test",
        "method_version": "hybrid_test",
        "assortment_version": "assortment_hybrid_test",
        "anchor_date": "2026-01-01",
        "effective_start_date": "2026-01-02",
        "effective_end_date": "2026-01-03",
        "fdc_id": "FDC1",
        "rdc_id": "RDC1",
        "sku_id": sku_id,
        "selected_flag": "true",
        "rank": rank,
        "score": 10 - rank,
        "topk_score": 10 - rank,
        "structure_score": 10 - rank,
        "ml_score": "",
        "source_tag": source_tag,
        "selected_k": 2,
        "candidate_sku_count": 3,
        "cumulative_volume": rank,
    }


def write_publish_inputs(run_dir: Path) -> None:
    write_csv(
        run_dir / "candidate_pool.csv",
        CANDIDATE_POOL_FIELDS,
        [
            candidate_row("SKU_A", 10),
            candidate_row("SKU_B", 9),
            candidate_row("SKU_C", 1),
        ],
    )
    write_csv(
        run_dir / "k_table.csv",
        K_TABLE_FIELDS,
        [
            {
                "experiment_id": "exp_publish",
                "data_version": "v_test",
                "candidate_pool_version": "candidate_pool_test",
                "k_rule_version": "k_rule_test",
                "anchor_date": "2026-01-01",
                "effective_start_date": "2026-01-02",
                "effective_end_date": "2026-01-03",
                "fdc_id": "FDC1",
                "rdc_id": "RDC1",
                "candidate_sku_count": 3,
                "target_order_coverage": 0.8,
                "capacity_volume_limit": 3,
                "avg_selected_sku_volume": 1,
                "physical_capacity_k": 2,
                "coverage_target_k": 2,
                "min_k": 1,
                "max_k": 2,
                "selected_k": 2,
                "k_source": "coverage",
                "historical_window_start": "2025-12-01",
                "historical_window_end": "2026-01-01",
            }
        ],
    )
    write_csv(run_dir / "hybrid_result.csv", TOPK_RESULT_FIELDS, [result_row("SKU_A", 1), result_row("SKU_B", 2)])


class PublishValidationTests(unittest.TestCase):
    def test_publish_assortment_result_and_validate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run_dir = root / "run"
            write_publish_inputs(run_dir)
            config = {
                "experiment_id": "exp_publish",
                "data_version": "v_test",
                "candidate_pool_version": "candidate_pool_test",
                "k_rule_version": "k_rule_test",
                "anchor_date": "2026-01-01",
                "effective_start_date": "2026-01-02",
                "effective_end_date": "2026-01-03",
                "publish": {"method": "hybrid", "config_path": "assortment/configs/test.yaml"},
                "output": {"report_dir": str(root / "reports")},
            }

            publish_summary = publish_assortment_result(config, run_dir)
            validation_summary = validate_assortment_run(Path(publish_summary["assortment_manifest"]))

            self.assertEqual(publish_summary["row_count"], 2)
            self.assertTrue((run_dir / "assortment_result.csv").exists())
            self.assertTrue(validation_summary["passed"])
            self.assertEqual(validation_summary["metrics"]["total_selected_rows"], 2)

    def test_validation_rejects_non_continuous_rank(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run_dir = root / "run"
            write_publish_inputs(run_dir)
            config = {
                "experiment_id": "exp_publish",
                "data_version": "v_test",
                "candidate_pool_version": "candidate_pool_test",
                "k_rule_version": "k_rule_test",
                "anchor_date": "2026-01-01",
                "effective_start_date": "2026-01-02",
                "effective_end_date": "2026-01-03",
                "publish": {"method": "hybrid"},
                "output": {"report_dir": str(root / "reports")},
            }
            publish_summary = publish_assortment_result(config, run_dir)
            rows = read_csv(run_dir / "assortment_result.csv")
            rows[1]["rank"] = "3"
            write_csv(run_dir / "assortment_result.csv", TOPK_RESULT_FIELDS, rows)

            validation_summary = validate_assortment_run(
                Path(publish_summary["assortment_manifest"]),
                write_outputs=False,
                update_manifest=False,
            )

            self.assertFalse(validation_summary["passed"])
            self.assertGreater(validation_summary["metrics"]["group_errors"], 0)


if __name__ == "__main__":
    unittest.main()
