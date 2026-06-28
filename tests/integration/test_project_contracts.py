from __future__ import annotations

import csv
import importlib.util
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
PROJECT_CONFIG = REPO_ROOT / "configs" / "project.yaml"


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise AssertionError(f"YAML file must be a mapping: {path}")
    return data


def load_runner_module():
    module_path = REPO_ROOT / "scripts" / "run_full_pipeline.py"
    spec = importlib.util.spec_from_file_location("run_full_pipeline_contract", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Cannot load runner module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProjectConfigContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_yaml(PROJECT_CONFIG)
        self.runner = load_runner_module()

    def test_project_config_declares_all_stage_commands(self) -> None:
        stage_order = self.config["pipeline"]["stage_order"]
        self.assertEqual(stage_order, ["data", "assortment", "simulation", "inventory", "evaluation"])
        stages = self.config["pipeline"]["stages"]
        self.assertEqual(set(stage_order), set(stages))

        context = self.runner.build_context(self.config)
        for stage_name in stage_order:
            stage = stages[stage_name]
            self.assertTrue(stage.get("commands"), stage_name)
            self.assertTrue(stage.get("expected_outputs"), stage_name)
            for step in stage["commands"]:
                rendered = self.runner.render_command(step["command"], context)
                self.assertNotIn("{", " ".join(rendered), rendered)
                self.assertNotIn("}", " ".join(rendered), rendered)
                self.assertEqual(rendered[0], "python3")
                script_path = REPO_ROOT / rendered[1]
                self.assertTrue(script_path.exists(), f"missing script for {stage_name}: {rendered[1]}")

    def test_declared_configs_docs_and_manifest_dirs_exist(self) -> None:
        for name, raw_path in self.config["configs"].items():
            self.assertTrue((REPO_ROOT / raw_path).exists(), f"missing config {name}: {raw_path}")

        engineering_docs = self.config["paths"]["engineering_docs"]
        for name, raw_path in engineering_docs.items():
            path = REPO_ROOT / raw_path
            self.assertTrue(path.exists(), f"missing engineering doc {name}: {raw_path}")
            self.assertGreater(path.stat().st_size, 0)

        for name, raw_path in self.config["paths"]["manifests"].items():
            path = REPO_ROOT / raw_path
            if name == "inventory" and not path.exists():
                self.assertTrue(path.parent.parent.exists(), f"missing inventory runs dir: {path.parent.parent}")
                continue
            self.assertTrue(path.exists(), f"missing manifest {name}: {raw_path}")

    def test_manifest_standards_cover_project_versions(self) -> None:
        doc_text = (REPO_ROOT / self.config["paths"]["engineering_docs"]["manifest_standards"]).read_text(
            encoding="utf-8"
        )
        for key in [
            "data_version",
            "split_version",
            "feature_version",
            "assortment_version",
            "simulation_rule_version",
            "inventory_version",
            "model_version",
            "evaluation_id",
            "experiment_id",
        ]:
            self.assertIn(key, doc_text)


class ManifestLineageContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_yaml(PROJECT_CONFIG)

    def test_existing_manifests_expose_required_version_lineage(self) -> None:
        manifests = self.config["paths"]["manifests"]
        data_manifest = load_yaml(REPO_ROOT / manifests["data"])
        assortment_manifest = load_yaml(REPO_ROOT / manifests["assortment"])
        simulation_manifest = load_yaml(REPO_ROOT / manifests["simulation"])
        evaluation_manifest = load_yaml(REPO_ROOT / manifests["evaluation"])

        self.assertEqual(data_manifest["data_version"], self.config["defaults"]["data_version"])
        self.assertEqual(assortment_manifest["data_version"], self.config["defaults"]["data_version"])
        self.assertEqual(assortment_manifest["assortment_version"], self.config["defaults"]["assortment_version"])
        self.assertEqual(simulation_manifest["data_version"], self.config["defaults"]["data_version"])
        self.assertEqual(simulation_manifest["simulation_rule_version"], self.config["defaults"]["simulation_rule_version"])

        protocol = evaluation_manifest["protocol"]
        for key in [
            "data_version",
            "split_version",
            "assortment_version",
            "inventory_version",
            "simulation_rule_version",
            "cost_config_version",
        ]:
            self.assertEqual(protocol[key], self.config["defaults"][key])
        self.assertEqual(evaluation_manifest["status"], "validated")

    def test_missing_inventory_run_is_explicit_in_evaluation_registry(self) -> None:
        inventory_manifest = REPO_ROOT / self.config["paths"]["manifests"]["inventory"]
        registry_path = REPO_ROOT / "evaluation" / "runs" / "eval_v001_baseline" / "experiment_registry.csv"
        self.assertTrue(registry_path.exists())

        with registry_path.open("r", encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        inventory_rows = [row for row in rows if row.get("stage") == "inventory"]
        self.assertEqual(len(inventory_rows), 1)
        if not inventory_manifest.exists():
            self.assertEqual(inventory_rows[0]["run_status"], "missing")
            self.assertIn("does not exist", inventory_rows[0]["notes"])


class RunnerLoggingContractTest(unittest.TestCase):
    run_id = "integration_contract_dry_run"

    def tearDown(self) -> None:
        log_dir = REPO_ROOT / "artifacts" / "run_logs"
        for suffix in [".jsonl", "_summary.json"]:
            path = log_dir / f"{self.run_id}{suffix}"
            if path.exists():
                path.unlink()

    def test_dry_run_writes_jsonl_and_summary_contract(self) -> None:
        env = os.environ.copy()
        env["PYTHONPATH"] = "."
        result = subprocess.run(
            [
                sys.executable,
                "scripts/run_full_pipeline.py",
                "--dry-run",
                "--run-id",
                self.run_id,
            ],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        log_path = REPO_ROOT / "artifacts" / "run_logs" / f"{self.run_id}.jsonl"
        summary_path = REPO_ROOT / "artifacts" / "run_logs" / f"{self.run_id}_summary.json"
        self.assertTrue(log_path.exists())
        self.assertTrue(summary_path.exists())

        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        self.assertEqual(summary["status"], "dry_run")
        self.assertEqual(summary["selected_stages"], ["data", "assortment", "simulation", "inventory", "evaluation"])
        self.assertEqual(len(summary["steps"]), 14)
        self.assertTrue(all(step["status"] == "dry_run" for step in summary["steps"]))

        events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
        event_names = [event["event"] for event in events]
        self.assertEqual(event_names.count("run_start"), 1)
        self.assertEqual(event_names.count("run_finish"), 1)
        self.assertEqual(event_names.count("step_start"), 14)
        self.assertEqual(event_names.count("step_finish"), 14)


class MakefileContractTest(unittest.TestCase):
    def test_makefile_runs_integration_tests(self) -> None:
        makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
        for target in ["data:", "assortment:", "simulation:", "inventory:", "evaluation:", "full:", "test:"]:
            self.assertIn(target, makefile)
        self.assertIn("tests/integration", makefile)


if __name__ == "__main__":
    unittest.main()
