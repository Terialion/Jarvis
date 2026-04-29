from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class ExternalBenchmarkFailureType(str, Enum):
    AGENT_FAILURE = "agent_failure"
    ADAPTER_FAILURE = "adapter_failure"
    ENVIRONMENT_FAILURE = "environment_failure"
    BENCHMARK_HARNESS_FAILURE = "benchmark_harness_failure"
    SKIPPED = "skipped"


@dataclass
class ExternalBenchmarkTask:
    instance_id: str
    repo: str
    base_commit: str
    problem_statement: str
    test_patch: str = ""
    hints_text: str = ""
    created_at: str = ""
    version: str = "lite"


@dataclass
class ExternalBenchmarkRunConfig:
    benchmark: str = "swebench_lite"
    dry_run: bool = True
    allow_online: bool = False
    skip_harness: bool = False
    max_tasks: int = 1
    task_id: str | None = None
    output_dir: str = "temp/external_benchmarks/swebench_lite"


@dataclass
class ExternalBenchmarkEvidence:
    operator_evidence_path: str = ""
    replay_evidence_path: str = ""
    patch_review_path: str = ""
    policy_evidence_path: str = ""
    prediction_evidence_path: str = ""
    harness_evidence_path: str = ""


@dataclass
class ExternalBenchmarkResult:
    schema_version: str = "jarvis.external_benchmark_result.v1"
    benchmark: str = "swebench_lite"
    task_id: str = ""
    instance_id: str = ""
    jarvis_run_id: str = ""
    status: str = "skipped"
    score: float = 0.0
    patch_generated: bool = False
    prediction_path: str = ""
    patch_path: str = ""
    raw_result_path: str = ""
    harness_result_path: str = ""
    operator_evidence_path: str = ""
    replay_evidence_path: str = ""
    patch_review_path: str = ""
    policy_violations: list[str] = field(default_factory=list)
    approval_events: list[dict[str, Any]] = field(default_factory=list)
    rollback_available: bool = False
    environment: dict[str, Any] = field(default_factory=dict)
    failure_type: str = ExternalBenchmarkFailureType.SKIPPED.value
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["updated_at"] = datetime.now().isoformat(timespec="seconds")
        return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(__import__("json").dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

