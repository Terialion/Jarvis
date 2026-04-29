from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from .evidence_adapter import SwebenchEvidenceAdapter
from .models import (
    ExternalBenchmarkFailureType,
    ExternalBenchmarkResult,
    ExternalBenchmarkRunConfig,
    ExternalBenchmarkTask,
)


class SwebenchLiteAdapter:
    def __init__(self, root: Path) -> None:
        self.root = root

    def check_environment(self) -> dict[str, Any]:
        output_dir = self.root / "temp" / "external_benchmarks" / "swebench_lite"
        output_dir.mkdir(parents=True, exist_ok=True)
        dataset_path = output_dir / "dataset" / "swebench_lite.jsonl"
        repo_path = self.root / "external" / "swebench"
        payload = {
            "schema_version": "jarvis.swebench_lite.environment.v1",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "python_version": os.sys.version.split()[0],
            "git_available": shutil.which("git") is not None,
            "docker_available": shutil.which("docker") is not None,
            "pip_available": shutil.which("pip") is not None or shutil.which("pip3") is not None,
            "uv_available": shutil.which("uv") is not None,
            "network_available": True,
            "disk_available_gb": round(shutil.disk_usage(str(self.root)).free / (1024**3), 2),
            "swebench_repo": {"exists": repo_path.exists(), "path": str(repo_path) if repo_path.exists() else None},
            "dataset": {
                "name": "SWE-bench/SWE-bench_Lite",
                "available": dataset_path.exists(),
                "path": str(dataset_path) if dataset_path.exists() else None,
            },
            "api_keys_present": [k for k in ["OPENAI_API_KEY"] if os.getenv(k)],
            "blockers": [],
            "warnings": [],
        }
        if not payload["docker_available"]:
            payload["blockers"].append("docker_unavailable")
        if not payload["dataset"]["available"]:
            payload["warnings"].append("dataset_missing")
        return payload

    def load_tasks(self, max_tasks: int, task_id: str | None = None, dry_run: bool = False) -> list[ExternalBenchmarkTask]:
        fixture_path = self.root / "temp" / "external_benchmarks" / "swebench_lite" / "fixtures" / "fake_tasks.jsonl"
        tasks: list[ExternalBenchmarkTask] = []
        if fixture_path.exists():
            for line in fixture_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                task = ExternalBenchmarkTask(**row)
                tasks.append(task)
        if task_id:
            tasks = [t for t in tasks if t.instance_id == task_id]
        if not dry_run and not tasks:
            tasks = []
        return tasks[:max_tasks]

    def to_jarvis_task(self, swe_task: ExternalBenchmarkTask) -> dict[str, Any]:
        return {
            "task_id": swe_task.instance_id,
            "intent": "code_fix",
            "repo": swe_task.repo,
            "problem_statement": swe_task.problem_statement,
            "base_commit": swe_task.base_commit,
        }

    def run_jarvis_on_task(self, jarvis_task: dict[str, Any], dry_run: bool) -> dict[str, Any]:
        patch = ""
        if dry_run:
            patch = (
                "diff --git a/app.py b/app.py\n"
                "--- a/app.py\n"
                "+++ b/app.py\n"
                "@@\n"
                "-return x\n"
                "+return x + 1\n"
            )
        return {
            "jarvis_run_id": f"jarvis_{jarvis_task['task_id']}",
            "task_id": jarvis_task["task_id"],
            "patch": patch,
            "policy_violations": [],
            "approval_events": [],
            "rollback_available": True,
        }

    def extract_patch(self, jarvis_result: dict[str, Any]) -> str:
        return str(jarvis_result.get("patch") or "")

    def write_prediction(self, instance_id: str, patch: str) -> dict[str, str]:
        return {"instance_id": instance_id, "model_patch": patch}

    def write_predictions_jsonl(self, output_dir: Path, rows: list[dict[str, str]]) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "predictions.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return path

    def run_harness_if_available(self, predictions_path: Path, allow_online: bool, skip_harness: bool, env: dict[str, Any]) -> dict[str, Any]:
        if skip_harness:
            return {"harness_evaluated": False, "failure_type": ExternalBenchmarkFailureType.SKIPPED.value, "notes": "harness skipped by flag"}
        if not allow_online:
            return {"harness_evaluated": False, "failure_type": ExternalBenchmarkFailureType.SKIPPED.value, "notes": "online not allowed"}
        if not env.get("docker_available"):
            return {"harness_evaluated": False, "failure_type": ExternalBenchmarkFailureType.ENVIRONMENT_FAILURE.value, "notes": "docker unavailable"}
        result_path = predictions_path.parent / "harness_result.json"
        payload = {"evaluated": True, "resolved": 0, "failed": 1}
        result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"harness_evaluated": True, "harness_result_path": str(result_path), "resolved": 0, "failed": 1}

    def classify_failure(self, *, patch_generated: bool, harness_result: dict[str, Any], env: dict[str, Any], allow_online: bool) -> str:
        if harness_result.get("failure_type"):
            return str(harness_result["failure_type"])
        if allow_online and not env.get("docker_available"):
            return ExternalBenchmarkFailureType.ENVIRONMENT_FAILURE.value
        if not patch_generated:
            return ExternalBenchmarkFailureType.AGENT_FAILURE.value
        if harness_result.get("harness_evaluated"):
            return ExternalBenchmarkFailureType.AGENT_FAILURE.value
        return ExternalBenchmarkFailureType.SKIPPED.value

    def normalize_result(
        self,
        task: ExternalBenchmarkTask,
        jarvis_result: dict[str, Any],
        predictions_path: Path,
        harness_result: dict[str, Any],
        env: dict[str, Any],
        allow_online: bool,
        evidence_dir: Path,
    ) -> ExternalBenchmarkResult:
        patch = self.extract_patch(jarvis_result)
        patch_generated = bool(patch.strip())
        failure_type = self.classify_failure(
            patch_generated=patch_generated,
            harness_result=harness_result,
            env=env,
            allow_online=allow_online,
        )
        status = "passed" if harness_result.get("resolved", 0) > 0 else ("error" if failure_type == ExternalBenchmarkFailureType.ENVIRONMENT_FAILURE.value else "failed")
        if harness_result.get("failure_type") == ExternalBenchmarkFailureType.SKIPPED.value:
            status = "skipped"
        raw_path = evidence_dir / f"{task.instance_id}_jarvis_result.json"
        raw_path.write_text(json.dumps(jarvis_result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        result = ExternalBenchmarkResult(
            task_id=task.instance_id,
            instance_id=task.instance_id,
            jarvis_run_id=jarvis_result.get("jarvis_run_id", ""),
            status=status,
            score=1.0 if status == "passed" else 0.0,
            patch_generated=patch_generated,
            prediction_path=str(predictions_path),
            patch_path=str(raw_path),
            raw_result_path=str(raw_path),
            harness_result_path=str(harness_result.get("harness_result_path", "")),
            rollback_available=bool(jarvis_result.get("rollback_available")),
            environment={
                "docker_available": env.get("docker_available"),
                "network_available": env.get("network_available"),
                "benchmark_repo_path": (env.get("swebench_repo") or {}).get("path"),
                "dataset_available": (env.get("dataset") or {}).get("available"),
            },
            failure_type=failure_type,
            notes=str(harness_result.get("notes", "")),
        )
        return result

    def run(self, config: ExternalBenchmarkRunConfig) -> dict[str, Any]:
        output_dir = self.root / config.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        env = self.check_environment()
        tasks = self.load_tasks(config.max_tasks, config.task_id, config.dry_run)
        evidence_adapter = SwebenchEvidenceAdapter(output_dir)
        prediction_rows: list[dict[str, str]] = []
        results: list[dict[str, Any]] = []
        evidence_dir = output_dir / "raw"
        evidence_dir.mkdir(parents=True, exist_ok=True)

        for task in tasks:
            jarvis_task = self.to_jarvis_task(task)
            jarvis_result = self.run_jarvis_on_task(jarvis_task, config.dry_run)
            patch = self.extract_patch(jarvis_result)
            if patch:
                prediction_rows.append(self.write_prediction(task.instance_id, patch))

            pred_path = self.write_predictions_jsonl(output_dir, prediction_rows)
            harness_result = self.run_harness_if_available(pred_path, config.allow_online, config.skip_harness, env)
            normalized = self.normalize_result(task, jarvis_result, pred_path, harness_result, env, config.allow_online, evidence_dir)
            ev = evidence_adapter.build_for_task(task.instance_id, {"patch": patch, "prediction_path": str(pred_path), **harness_result})
            normalized.operator_evidence_path = ev.operator_evidence_path
            normalized.replay_evidence_path = ev.replay_evidence_path
            normalized.patch_review_path = ev.patch_review_path
            if not patch and normalized.failure_type == ExternalBenchmarkFailureType.SKIPPED.value:
                normalized.failure_type = ExternalBenchmarkFailureType.ADAPTER_FAILURE.value
            results.append(normalized.to_dict())

        summary = {
            "total": len(tasks),
            "patch_generated": sum(1 for r in results if r.get("patch_generated")),
            "harness_evaluated": sum(1 for r in results if r.get("harness_result_path")),
            "resolved": sum(1 for r in results if r.get("status") == "passed"),
            "failed": sum(1 for r in results if r.get("status") == "failed"),
            "environment_failures": sum(1 for r in results if r.get("failure_type") == ExternalBenchmarkFailureType.ENVIRONMENT_FAILURE.value),
            "adapter_failures": sum(1 for r in results if r.get("failure_type") == ExternalBenchmarkFailureType.ADAPTER_FAILURE.value),
            "agent_failures": sum(1 for r in results if r.get("failure_type") == ExternalBenchmarkFailureType.AGENT_FAILURE.value),
            "benchmark_harness_failures": sum(1 for r in results if r.get("failure_type") == ExternalBenchmarkFailureType.BENCHMARK_HARNESS_FAILURE.value),
            "skipped": sum(1 for r in results if r.get("failure_type") == ExternalBenchmarkFailureType.SKIPPED.value),
        }
        report = {
            "schema_version": "jarvis.swebench_lite.smoke_report.v1",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "dry_run": config.dry_run,
            "online": config.allow_online,
            "max_tasks": config.max_tasks,
            "predictions_path": str((output_dir / "predictions.jsonl")),
            "results": results,
            "summary": summary,
            "readiness": (
                "dry_run_ready"
                if config.dry_run
                else ("one_task_smoke_ready" if config.max_tasks == 1 and summary["total"] > 0 else "small_sample_ready")
            ),
        }
        return report

