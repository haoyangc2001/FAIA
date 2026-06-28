#!/usr/bin/env python3
"""Run the staged FAIA project pipeline from the repository root."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


class FormatMap(dict):
    """Format helper that supports {config:data} and {manifest:data} tokens."""

    def __init__(self, context: dict[str, Any]) -> None:
        super().__init__(context)
        self.context = context

    def __missing__(self, key: str) -> str:
        if ":" in key:
            section, name = key.split(":", 1)
            value = self.context.get(section, {}).get(name)
            if value is not None:
                return str(value)
        value = self.context.get(key)
        if value is not None:
            return str(value)
        return "{" + key + "}"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config must be a YAML mapping: {path}")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def append_jsonl(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False, sort_keys=True))
        f.write("\n")


def tail_lines(text: str, limit: int) -> str:
    if limit <= 0:
        return ""
    lines = text.splitlines()
    return "\n".join(lines[-limit:])


def resolve_repo_root(config: dict[str, Any]) -> Path:
    root_value = str(config.get("project", {}).get("root", "."))
    root_path = Path(root_value)
    if root_path.is_absolute():
        return root_path
    return (Path.cwd() / root_path).resolve()


def build_context(config: dict[str, Any]) -> dict[str, Any]:
    defaults = config.get("defaults", {}) or {}
    paths = config.get("paths", {}) or {}
    return {
        "python": config.get("project", {}).get("python", "python3"),
        "config": config.get("configs", {}) or {},
        "manifest": paths.get("manifests", {}) or {},
        "data_version": defaults.get("data_version", "v001"),
        "split_version": defaults.get("split_version", "split_v001"),
        "evaluation_id": defaults.get("evaluation_id", "eval_v001_baseline"),
        "assortment_version": defaults.get("assortment_version", "assortment_hybrid_v001"),
        "inventory_version": defaults.get("inventory_version", "inventory_base_stock_v001"),
        "simulation_rule_version": defaults.get("simulation_rule_version", "sim_rule_v001"),
    }


def render_command(command: list[Any], context: dict[str, Any]) -> list[str]:
    mapping = FormatMap(context)
    rendered: list[str] = []
    for part in command:
        value = str(part)
        for section in ("config", "manifest"):
            for name, path in (context.get(section, {}) or {}).items():
                value = value.replace("{" + section + ":" + name + "}", str(path))
        rendered.append(value.format_map(mapping))
    return rendered


def parse_stage_args(raw_stages: list[str] | None) -> list[str] | None:
    if not raw_stages:
        return None
    stages: list[str] = []
    for raw in raw_stages:
        stages.extend(part.strip() for part in raw.split(",") if part.strip())
    return stages or None


def select_stages(
    stage_order: list[str],
    requested: list[str] | None,
    from_stage: str | None,
    to_stage: str | None,
) -> list[str]:
    selected = list(stage_order)
    if requested:
        unknown = sorted(set(requested) - set(stage_order))
        if unknown:
            raise ValueError(f"Unknown stage(s): {', '.join(unknown)}")
        selected = requested
    if from_stage:
        if from_stage not in selected:
            raise ValueError(f"--from-stage is not in the selected stage list: {from_stage}")
        selected = selected[selected.index(from_stage) :]
    if to_stage:
        if to_stage not in selected:
            raise ValueError(f"--to-stage is not in the selected stage list: {to_stage}")
        selected = selected[: selected.index(to_stage) + 1]
    return selected


def make_env(config: dict[str, Any]) -> dict[str, str]:
    env = os.environ.copy()
    for key, value in (config.get("execution", {}).get("env", {}) or {}).items():
        env[str(key)] = str(value)
    pythonpath = config.get("project", {}).get("pythonpath")
    if pythonpath:
        env["PYTHONPATH"] = str(pythonpath)
    return env


def run_step(
    *,
    stage_name: str,
    step: dict[str, Any],
    command: list[str],
    repo_root: Path,
    env: dict[str, str],
    log_path: Path,
    dry_run: bool,
    stdout_tail_limit: int,
    stderr_tail_limit: int,
) -> dict[str, Any]:
    step_name = str(step.get("name", "unnamed_step"))
    started_at = now_iso()
    start = time.monotonic()
    append_jsonl(
        log_path,
        {
            "event": "step_start",
            "stage": stage_name,
            "step": step_name,
            "command": command,
            "started_at": started_at,
            "dry_run": dry_run,
        },
    )
    print(f"[{stage_name}] {step_name}: {' '.join(command)}")

    if dry_run:
        result = {
            "stage": stage_name,
            "step": step_name,
            "command": command,
            "status": "dry_run",
            "return_code": 0,
            "started_at": started_at,
            "finished_at": now_iso(),
            "duration_seconds": 0.0,
        }
        append_jsonl(log_path, {"event": "step_finish", **result})
        return result

    completed = subprocess.run(
        command,
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    duration = round(time.monotonic() - start, 3)
    status = "passed" if completed.returncode == 0 else "failed"
    result = {
        "stage": stage_name,
        "step": step_name,
        "command": command,
        "status": status,
        "return_code": completed.returncode,
        "started_at": started_at,
        "finished_at": now_iso(),
        "duration_seconds": duration,
        "stdout_tail": tail_lines(completed.stdout, stdout_tail_limit),
        "stderr_tail": tail_lines(completed.stderr, stderr_tail_limit),
    }
    append_jsonl(log_path, {"event": "step_finish", **result})
    print(f"[{stage_name}] {step_name}: {status} ({duration}s)")
    if completed.returncode and result["stderr_tail"]:
        print(result["stderr_tail"], file=sys.stderr)
    return result


def check_expected_outputs(repo_root: Path, expected_outputs: list[str]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for raw_path in expected_outputs:
        path = repo_root / raw_path
        checks.append(
            {
                "path": raw_path,
                "exists": path.exists(),
                "bytes": path.stat().st_size if path.exists() else 0,
            }
        )
    return checks


def relpath(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def run_pipeline(args: argparse.Namespace) -> dict[str, Any]:
    config_path = Path(args.config).resolve()
    config = read_yaml(config_path)
    repo_root = resolve_repo_root(config)
    pipeline = config.get("pipeline", {}) or {}
    stage_order = list(pipeline.get("stage_order", []))
    stages_config = pipeline.get("stages", {}) or {}
    if not stage_order:
        raise ValueError("pipeline.stage_order must not be empty")

    selected_stages = select_stages(stage_order, parse_stage_args(args.stages), args.from_stage, args.to_stage)
    missing_stage_configs = sorted(set(selected_stages) - set(stages_config))
    if missing_stage_configs:
        raise ValueError(f"Selected stage(s) missing from pipeline.stages: {', '.join(missing_stage_configs)}")

    paths = config.get("paths", {}) or {}
    run_logs_dir = repo_root / str(paths.get("run_logs_dir", "artifacts/run_logs"))
    run_id = args.run_id or datetime.now().strftime("pipeline_%Y%m%d_%H%M%S")
    log_path = run_logs_dir / f"{run_id}.jsonl"
    summary_path = run_logs_dir / f"{run_id}_summary.json"
    context = build_context(config)
    env = make_env(config)
    execution = config.get("execution", {}) or {}
    stdout_tail_limit = int(execution.get("stdout_tail_lines", 80))
    stderr_tail_limit = int(execution.get("stderr_tail_lines", 80))
    continue_on_error = bool(args.continue_on_error)

    summary: dict[str, Any] = {
        "run_id": run_id,
        "config": relpath(config_path, repo_root),
        "repo_root": str(repo_root),
        "started_at": now_iso(),
        "finished_at": None,
        "dry_run": bool(args.dry_run),
        "status": "running",
        "selected_stages": selected_stages,
        "steps": [],
        "stage_outputs": {},
        "log_path": relpath(log_path, repo_root),
        "summary_path": relpath(summary_path, repo_root),
    }
    append_jsonl(log_path, {"event": "run_start", **summary})

    for stage_name in selected_stages:
        stage = stages_config[stage_name]
        commands = stage.get("commands", []) or []
        print(f"== Stage: {stage_name} ==")
        for step in commands:
            command = render_command(list(step["command"]), context)
            result = run_step(
                stage_name=stage_name,
                step=step,
                command=command,
                repo_root=repo_root,
                env=env,
                log_path=log_path,
                dry_run=bool(args.dry_run),
                stdout_tail_limit=stdout_tail_limit,
                stderr_tail_limit=stderr_tail_limit,
            )
            summary["steps"].append(result)
            if result["return_code"] != 0 and not continue_on_error:
                summary["status"] = "failed"
                summary["failed_stage"] = stage_name
                summary["failed_step"] = result["step"]
                summary["finished_at"] = now_iso()
                write_json(summary_path, summary)
                append_jsonl(log_path, {"event": "run_finish", **summary})
                raise SystemExit(result["return_code"])
        if not args.dry_run:
            expected_outputs = list(stage.get("expected_outputs", []) or [])
            summary["stage_outputs"][stage_name] = check_expected_outputs(repo_root, expected_outputs)

    failed_steps = [step for step in summary["steps"] if step["return_code"] != 0]
    summary["status"] = "failed" if failed_steps else "dry_run" if args.dry_run else "passed"
    summary["finished_at"] = now_iso()
    if failed_steps:
        summary["failed_stage"] = failed_steps[0]["stage"]
        summary["failed_step"] = failed_steps[0]["step"]
    write_json(summary_path, summary)
    append_jsonl(log_path, {"event": "run_finish", **summary})
    print(json.dumps({"status": summary["status"], "summary_path": summary["summary_path"]}, ensure_ascii=False, indent=2))
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the FAIA staged project pipeline.")
    parser.add_argument("--config", default="configs/project.yaml", help="Path to project config.")
    parser.add_argument("--stages", nargs="*", help="Stage names or comma-separated stage list.")
    parser.add_argument("--stage", action="append", dest="stages", help="Alias for --stages; can be repeated.")
    parser.add_argument("--from-stage", default=None, help="Start from this selected stage.")
    parser.add_argument("--to-stage", default=None, help="Stop after this selected stage.")
    parser.add_argument("--run-id", default=None, help="Optional run id for log file names.")
    parser.add_argument("--dry-run", action="store_true", help="Print and log commands without executing them.")
    parser.add_argument("--continue-on-error", action="store_true", help="Continue after failed steps.")
    parser.add_argument("--list-stages", action="store_true", help="List configured stages and exit.")
    args = parser.parse_args()

    if args.list_stages:
        config = read_yaml(Path(args.config).resolve())
        for stage in config.get("pipeline", {}).get("stage_order", []) or []:
            print(stage)
        raise SystemExit(0)
    return args


def main() -> None:
    args = parse_args()
    try:
        run_pipeline(args)
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"pipeline error: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
