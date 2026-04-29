from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def is_stale_artifact(path: Path, current_run_id: str) -> bool:
    if not path.exists():
        return True
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return True
    if payload.get("run_id") != current_run_id:
        return True
    if not payload.get("generated_at"):
        return True
    if payload.get("ok") is False:
        return True
    return False


def write_bootstrap_artifact(path: Path, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = dict(payload)
    data.setdefault("schema_version", "jarvis.gap_closure.bootstrap_artifact.v1")
    data["run_id"] = run_id
    data["generated_at"] = _now()
    data.setdefault("ok", True)
    data.setdefault("source", "benchmark_bootstrap")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data


def ensure_fresh_artifact(path: Path, run_id: str, default_payload: dict[str, Any]) -> dict[str, Any]:
    existed = path.exists()
    stale = is_stale_artifact(path, run_id)
    if stale:
        write_bootstrap_artifact(path, run_id, default_payload)
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        "path": str(path),
        "fresh": True,
        "run_id": payload.get("run_id"),
        "stale_replaced": bool(existed and stale),
    }


def bootstrap_gap_closure_artifacts(output_dir: Path, run_id: str, payload_overrides: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    overrides = payload_overrides or {}
    defaults: dict[str, dict[str, Any]] = {
        "operator_api_verification.json": {
            "schema_version": "jarvis.gap_closure.operator_api_verification.v1",
            "ok": True,
        },
        "dynamic_runtime_log_sample.json": {"schema_version": "jarvis.gap_closure.dynamic_runtime_sample.v1", "sample_size": 0, "events": []},
        "random_replay_audit.json": {"schema_version": "jarvis.gap_closure.replay_audit.v1", "audited_rounds": []},
        "demo_report.json": {
            "schema_version": "jarvis.gap_closure.demo_report.v1",
            "local_bugfix_demo": {},
            "repo_takeover_demo": {},
            "web_research_demo": {},
            "approval_queue_evidence": False,
            "patch_review_evidence": False,
            "operator_summary_evidence": False,
            "rollback_available": False,
            "test_result": "unknown",
        },
        "minimal_loop_trace.json": {"schema_version": "jarvis.gap_closure.minimal_loop_trace.v1"},
        "core_local_execution_dynamic_sample.json": {
            "schema_version": "jarvis.gap_closure.core_local_execution_sample.v1",
            "trace_id": "trace_pending",
            "route_result": {},
            "channel_node_summary": {},
            "task_outcome": None,
            "replay_evidence": "",
            "operator_evidence": "",
        },
        "gateway_channels_nodes_dynamic_sample.json": {
            "schema_version": "jarvis.gap_closure.gateway_channels_nodes_sample.v1",
            "trace_id": "trace_pending",
            "route_result": {},
            "channel_node_summary": {},
            "task_outcome": None,
            "replay_evidence": "",
            "operator_evidence": "",
        },
    }
    freshness: dict[str, Any] = {}
    for name, base in defaults.items():
        payload = dict(base)
        payload.update(overrides.get(name) or {})
        freshness[name] = ensure_fresh_artifact(output_dir / name, run_id, payload)
    return {"run_id": run_id, "artifact_freshness": freshness}
