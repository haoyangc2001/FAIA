from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

import yaml

from evaluation.src.collect import REGISTRY_FIELDS, collect_results
from evaluation.src.compare import COMPARISON_FIELDS
from evaluation.src.metrics import METRIC_FIELDS
from evaluation.src.report import build_evaluation_report
from evaluation.src.validation import validate_evaluation_run


def write_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


class EvaluationCollectorTest(unittest.TestCase):
    def test_collects_registry_metrics_and_comparison_with_missing_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "doc").mkdir()
            config_path = root / "evaluation/configs/evaluation_default.yaml"
            write_yaml(
                config_path,
                {
                    "evaluation_id": "eval_test",
                    "evaluation_version": "evaluation_protocol_test",
                    "data_version": "vtest",
                    "split_version": "split_vtest",
                    "evaluation_split": "test",
                    "evaluation_window": {"start_date": "2026-01-02", "end_date": "2026-01-03"},
                    "versions": {
                        "candidate_pool_version": "candidate_pool_test",
                        "k_rule_version": "k_rule_test",
                        "assortment_version": "assortment_hybrid_test",
                        "inventory_version": "inventory_base_stock_test",
                        "simulation_rule_version": "sim_rule_test",
                        "cost_config_version": "cost_config_test",
                        "cost_config_path": "data/synthetic/vtest/cost_config.csv",
                    },
                    "comparison_protocol": {"missing_run_status": "missing"},
                    "manifest_sources": {
                        "data": ["data/versions/vtest/manifest.yaml"],
                        "assortment": ["assortment/runs/assortment_test/assortment_manifest.yaml"],
                        "simulation": ["simulation/runs/sim_test/simulation_manifest.yaml"],
                        "inventory": ["inventory/runs/inventory_test/inventory_manifest.yaml"],
                    },
                    "baseline_matrix": {
                        "assortment_methods": [
                            {
                                "method_name": "hybrid",
                                "method_family": "heuristic",
                                "expected_assortment_version": "assortment_hybrid_test",
                            }
                        ],
                        "inventory_methods": [
                            {
                                "method_name": "no_transfer",
                                "method_family": "baseline",
                                "expected_inventory_version": "inventory_no_transfer_test",
                            },
                            {
                                "method_name": "base_stock",
                                "method_family": "heuristic",
                                "expected_inventory_version": "inventory_base_stock_test",
                            },
                        ],
                        "combination_experiments": [
                            {
                                "combination_id": "hybrid_base_stock",
                                "assortment_method": "hybrid",
                                "inventory_method": "base_stock",
                                "expected_status": "planned",
                            }
                        ],
                    },
                    "expected_outputs": {
                        "experiment_registry": "evaluation/runs/eval_test/experiment_registry.csv",
                        "metrics_summary": "evaluation/runs/eval_test/metrics_summary.csv",
                        "comparison_table": "evaluation/runs/eval_test/comparison_table.csv",
                        "evaluation_manifest": "evaluation/runs/eval_test/evaluation_manifest.yaml",
                        "evaluation_validation_summary": "evaluation/runs/eval_test/evaluation_validation_summary.json",
                        "evaluation_validation_report": "evaluation/reports/eval_test_validation_report.md",
                        "evaluation_report": "evaluation/reports/eval_test_report.md",
                    },
                },
            )

            write_yaml(
                root / "data/versions/vtest/manifest.yaml",
                {
                    "data_version": "vtest",
                    "registered_at": "2026-01-01T00:00:00",
                    "artifacts": {
                        "synthetic": {
                            "counts": {
                                "sku_master": 2,
                                "orders": 3,
                                "order_items": 4,
                                "warehouse_master": 2,
                                "stockout_events": 1,
                            }
                        },
                        "processed": {
                            "counts": {
                                "candidate_pool_base": 5,
                                "fdc_sku_daily_demand": 6,
                                "inventory_daily_state": 7,
                            }
                        },
                        "splits": {"counts": {"train_dates": 1, "val_dates": 1, "test_dates": 2}},
                    },
                    "validation": {
                        "status": "PASS",
                        "total_checks": 4,
                        "failed_checks": 0,
                        "warnings": 0,
                        "summary": "data/validation/vtest_summary.json",
                    },
                },
            )
            write_yaml(
                root / "assortment/runs/assortment_test/assortment_manifest.yaml",
                {
                    "experiment_id": "assortment_test",
                    "created_at": "2026-01-01T01:00:00",
                    "data_version": "vtest",
                    "candidate_pool_version": "candidate_pool_test",
                    "k_rule_version": "k_rule_test",
                    "method": "hybrid",
                    "assortment_version": "assortment_hybrid_test",
                    "run_dir": "assortment/runs/assortment_test",
                    "outputs": {"assortment_metrics": "assortment/runs/assortment_test/assortment_metrics.json"},
                    "row_counts": {"assortment_result": 2},
                    "validation": {"passed": True},
                },
            )
            write_yaml(
                root / "assortment/runs/assortment_test/run_manifest.yaml",
                {
                    "experiment_id": "assortment_test",
                    "data_version": "vtest",
                    "candidate_pool_version": "candidate_pool_test",
                    "k_rule_version": "k_rule_test",
                    "method_versions": {"hybrid": "hybrid_test"},
                    "assortment_versions": {"hybrid": "assortment_hybrid_test"},
                    "hybrid_summary": {"row_count": 2, "fdc_count": 1, "total_selected_rows": 2},
                },
            )
            write_json(
                root / "simulation/runs/sim_test/metrics_summary.json",
                {
                    "experiment_id": "sim_test",
                    "data_version": "vtest",
                    "assortment_version": "assortment_hybrid_test",
                    "policy_version": "no_transfer_test",
                    "simulation_rule_version": "sim_rule_test",
                    "simulation_start_date": "2026-01-02",
                    "simulation_end_date": "2026-01-03",
                    "total_demand_qty": 10,
                    "fdc_fulfilled_qty": 2,
                    "rdc_fallback_qty": 3,
                    "lost_sales_qty": 5,
                    "fdc_fulfillment_rate": 0.2,
                    "loss_ratio": 0.5,
                    "transfer_cost": 0.0,
                    "rdc_fallback_cost": 3.0,
                    "lost_sales_cost": 5.0,
                    "holding_cost": 1.0,
                    "total_cost": 9.0,
                },
            )
            write_yaml(
                root / "simulation/runs/sim_test/simulation_manifest.yaml",
                {
                    "experiment_id": "sim_test",
                    "created_at": "2026-01-01T02:00:00",
                    "data_version": "vtest",
                    "assortment_version": "assortment_hybrid_test",
                    "policy_version": "no_transfer_test",
                    "simulation_rule_version": "sim_rule_test",
                    "simulation_start_date": "2026-01-02",
                    "simulation_end_date": "2026-01-03",
                    "run_dir": "simulation/runs/sim_test",
                    "outputs": {"metrics_summary": {"path": "simulation/runs/sim_test/metrics_summary.json"}},
                    "row_counts": {"daily_state": 2},
                    "validation": {"passed": True},
                },
            )

            manifest = collect_results(config_path)
            self.assertEqual(manifest["status"], "collected")
            self.assertEqual(manifest["row_counts"]["experiment_registry"], 4)
            self.assertGreater(manifest["row_counts"]["metrics_summary"], 0)

            registry = read_csv(root / "evaluation/runs/eval_test/experiment_registry.csv")
            inventory_row = next(row for row in registry if row["stage"] == "inventory")
            self.assertEqual(inventory_row["run_status"], "missing")

            comparison = read_csv(root / "evaluation/runs/eval_test/comparison_table.csv")
            no_transfer = next(row for row in comparison if row["comparison_id"] == "no_transfer")
            self.assertEqual(no_transfer["run_status"], "available")
            self.assertEqual(no_transfer["fdc_fulfillment_rate"], "0.2")
            base_stock = next(row for row in comparison if row["comparison_id"] == "base_stock")
            self.assertEqual(base_stock["run_status"], "missing")

            manifest_path = root / "evaluation/runs/eval_test/evaluation_manifest.yaml"
            report_summary = build_evaluation_report(manifest_path)
            self.assertTrue((root / report_summary["report_path"]).exists())

            validation_summary = validate_evaluation_run(manifest_path)
            self.assertTrue(validation_summary["passed"])
            self.assertTrue((root / "evaluation/runs/eval_test/evaluation_validation_summary.json").exists())
            self.assertTrue((root / "evaluation/reports/eval_test_validation_report.md").exists())

    def test_validation_accepts_available_inventory_with_shorter_effective_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "doc").mkdir()
            run_dir = root / "evaluation/runs/eval_test"
            report_path = root / "evaluation/reports/eval_test_report.md"
            validation_report_path = root / "evaluation/reports/eval_test_validation_report.md"
            manifest_path = run_dir / "evaluation_manifest.yaml"
            registry_path = run_dir / "experiment_registry.csv"
            metrics_path = run_dir / "metrics_summary.csv"
            comparison_path = run_dir / "comparison_table.csv"

            protocol = {
                "data_version": "vtest",
                "split_version": "split_vtest",
                "evaluation_split": "test",
                "evaluation_window": {"start_date": "2026-01-02", "end_date": "2026-01-31"},
                "candidate_pool_version": "candidate_pool_test",
                "k_rule_version": "k_rule_test",
                "assortment_version": "assortment_hybrid_test",
                "inventory_version": "inventory_base_stock_test",
                "simulation_rule_version": "sim_rule_test",
                "cost_config_version": "cost_config_test",
            }
            common_registry = {
                "evaluation_id": "eval_test",
                "run_status": "available",
                "data_version": "vtest",
                "split_version": "split_vtest",
                "candidate_pool_version": "candidate_pool_test",
                "k_rule_version": "k_rule_test",
                "assortment_version": "assortment_hybrid_test",
                "inventory_version": "inventory_base_stock_test",
                "simulation_rule_version": "sim_rule_test",
                "cost_config_version": "cost_config_test",
                "evaluation_split": "test",
                "evaluation_start_date": "2026-01-02",
                "evaluation_end_date": "2026-01-31",
                "validation_status": "PASS",
            }
            write_csv(
                registry_path,
                REGISTRY_FIELDS,
                [
                    {
                        **common_registry,
                        "stage": "data",
                        "experiment_id": "vtest",
                        "method_name": "data_version",
                        "method_family": "data_artifact",
                    },
                    {
                        **common_registry,
                        "stage": "assortment",
                        "experiment_id": "assortment_test",
                        "method_name": "hybrid",
                        "method_family": "heuristic",
                    },
                    {
                        **common_registry,
                        "stage": "simulation",
                        "experiment_id": "sim_test",
                        "method_name": "no_transfer",
                        "method_family": "baseline",
                        "policy_version": "no_transfer_test",
                    },
                    {
                        **common_registry,
                        "stage": "inventory",
                        "experiment_id": "inventory_test",
                        "method_name": "base_stock",
                        "method_family": "heuristic",
                        "policy_version": "inventory_base_stock_test",
                        "evaluation_end_date": "2026-01-08",
                    },
                ],
            )

            def metric(stage: str, method_name: str, name: str, value: object, unit: str) -> dict[str, object]:
                return {
                    "evaluation_id": "eval_test",
                    "stage": stage,
                    "experiment_id": f"{stage}_test",
                    "run_status": "available",
                    "method_name": method_name,
                    "method_family": "baseline" if method_name == "no_transfer" else "heuristic",
                    "data_version": "vtest",
                    "split_version": "split_vtest",
                    "candidate_pool_version": "candidate_pool_test",
                    "k_rule_version": "k_rule_test",
                    "assortment_version": "assortment_hybrid_test",
                    "inventory_version": "inventory_base_stock_test",
                    "simulation_rule_version": "sim_rule_test",
                    "cost_config_version": "cost_config_test",
                    "evaluation_split": "test",
                    "evaluation_start_date": "2026-01-02",
                    "evaluation_end_date": "2026-01-08" if stage == "inventory" else "2026-01-31",
                    "metric_level": "overall",
                    "metric_key": "ALL",
                    "metric_name": name,
                    "metric_value": value,
                    "metric_unit": unit,
                }

            write_csv(
                metrics_path,
                METRIC_FIELDS,
                [
                    metric("data", "data_version", "num_orders", 3, "count"),
                    metric("data", "data_version", "num_order_items", 4, "count"),
                    metric("data", "data_version", "num_skus", 2, "count"),
                    metric("data", "data_version", "validation_error_count", 0, "count"),
                    metric("simulation", "no_transfer", "total_demand_qty", 10, "qty"),
                    metric("simulation", "no_transfer", "fdc_fulfilled_qty", 2, "qty"),
                    metric("simulation", "no_transfer", "rdc_fallback_qty", 3, "qty"),
                    metric("simulation", "no_transfer", "lost_sales_qty", 5, "qty"),
                    metric("simulation", "no_transfer", "fdc_fulfillment_rate", 0.2, "ratio"),
                    metric("simulation", "no_transfer", "loss_ratio", 0.5, "ratio"),
                    metric("simulation", "no_transfer", "transfer_cost", 0, "cost"),
                    metric("simulation", "no_transfer", "rdc_fallback_cost", 3, "cost"),
                    metric("simulation", "no_transfer", "lost_sales_cost", 5, "cost"),
                    metric("simulation", "no_transfer", "holding_cost", 1, "cost"),
                    metric("simulation", "no_transfer", "total_cost", 9, "cost"),
                    metric("inventory", "base_stock", "transfer_recommendation_rows", 7, "count"),
                ],
            )
            write_csv(
                comparison_path,
                COMPARISON_FIELDS,
                [
                    {
                        "evaluation_id": "eval_test",
                        "comparison_type": "inventory_method",
                        "comparison_id": "no_transfer",
                        "run_status": "available",
                        "metrics_status": "available",
                        "method_name": "no_transfer",
                        "inventory_method": "no_transfer",
                    }
                ],
            )
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text("# Evaluation Report\n", encoding="utf-8")
            write_yaml(
                manifest_path,
                {
                    "evaluation_id": "eval_test",
                    "status": "collected",
                    "protocol": protocol,
                    "row_counts": {
                        "experiment_registry": 4,
                        "metrics_summary": 16,
                        "comparison_table": 1,
                    },
                    "expected_outputs": {
                        "experiment_registry": "evaluation/runs/eval_test/experiment_registry.csv",
                        "metrics_summary": "evaluation/runs/eval_test/metrics_summary.csv",
                        "comparison_table": "evaluation/runs/eval_test/comparison_table.csv",
                        "evaluation_report": "evaluation/reports/eval_test_report.md",
                        "evaluation_validation_summary": "evaluation/runs/eval_test/evaluation_validation_summary.json",
                        "evaluation_validation_report": "evaluation/reports/eval_test_validation_report.md",
                    },
                },
            )

            validation_summary = validate_evaluation_run(manifest_path)

            self.assertTrue(validation_summary["passed"], validation_summary["checks"])
            self.assertTrue(validation_report_path.exists())


if __name__ == "__main__":
    unittest.main()
