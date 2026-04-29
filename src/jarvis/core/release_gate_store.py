"""Persistence helpers for Phase 1 acceptance/release-gate summaries."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

from .result import error_result, ok_result


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _state_dir(project_root: str | Path | None = None) -> Path:
    root = Path(project_root or ".").resolve()
    return root / ".jarvis" / "state"


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def write_release_gate_summary(summary: dict, project_root: str | Path | None = None) -> dict:
    started = perf_counter()
    if not isinstance(summary, dict):
        return error_result(
            "COMMON_INVALID_INPUT",
            "summary must be a dict",
            {"received_type": str(type(summary))},
            started,
        )
    target_dir = _state_dir(project_root)
    target_dir.mkdir(parents=True, exist_ok=True)
    payload = {"gate_name": "phase1_release_gate", "run_at": _utc_now(), **summary}
    target = target_dir / "phase1_release_gate_summary.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return ok_result({"path": str(target), "summary": payload}, started)


def write_acceptance_summary(summary: dict, project_root: str | Path | None = None) -> dict:
    started = perf_counter()
    if not isinstance(summary, dict):
        return error_result(
            "COMMON_INVALID_INPUT",
            "summary must be a dict",
            {"received_type": str(type(summary))},
            started,
        )
    target_dir = _state_dir(project_root)
    target_dir.mkdir(parents=True, exist_ok=True)
    payload = {"gate_name": "phase1_acceptance", "run_at": _utc_now(), **summary}
    target = target_dir / "phase1_acceptance_summary.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return ok_result({"path": str(target), "summary": payload}, started)


def read_release_gate_summary(project_root: str | Path | None = None) -> dict:
    started = perf_counter()
    target = _state_dir(project_root) / "phase1_release_gate_summary.json"
    if not target.exists():
        return ok_result(None, started)
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        return ok_result(payload, started)
    except Exception as exc:
        return error_result(
            "COMMON_INTERNAL_ERROR",
            "Failed to parse release gate summary",
            {"path": str(target), "exception": str(exc)},
            started,
        )


def read_acceptance_summary(project_root: str | Path | None = None) -> dict:
    started = perf_counter()
    target = _state_dir(project_root) / "phase1_acceptance_summary.json"
    if not target.exists():
        return ok_result(None, started)
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        return ok_result(payload, started)
    except Exception as exc:
        return error_result(
            "COMMON_INTERNAL_ERROR",
            "Failed to parse acceptance summary",
            {"path": str(target), "exception": str(exc)},
            started,
        )


def merge_gate_views(
    release_gate_summary: dict | None,
    acceptance_summary: dict | None,
) -> dict:
    """Provide a normalized gate summary payload for control-surface consumers."""
    if not release_gate_summary and not acceptance_summary:
        return {}
    if release_gate_summary:
        acceptance = release_gate_summary.get("acceptance") or {}
        regression = release_gate_summary.get("regression") or {}
        return {
            "gate_name": release_gate_summary.get("gate_name", "phase1_release_gate"),
            "passed": _safe_bool(release_gate_summary.get("passed")),
            "headline": release_gate_summary.get("headline"),
            "first_failure": release_gate_summary.get("first_failure"),
            "run_at": release_gate_summary.get("run_at"),
            "duration_ms": _safe_int(release_gate_summary.get("duration_ms")),
            "acceptance": {
                "passed": _safe_bool(acceptance.get("passed")),
                "summary_line": acceptance.get("summary_line"),
                "first_failure": acceptance.get("first_failure"),
                "duration_ms": _safe_int(acceptance.get("duration_ms")),
            },
            "regression": {
                "passed": _safe_bool(regression.get("passed")),
                "summary_line": regression.get("summary_line"),
                "first_failure": regression.get("first_failure"),
                "duration_ms": _safe_int(regression.get("duration_ms")),
            },
        }
    return {
        "gate_name": acceptance_summary.get("gate_name", "phase1_acceptance"),
        "passed": _safe_bool(acceptance_summary.get("passed")),
        "headline": acceptance_summary.get("headline"),
        "first_failure": acceptance_summary.get("first_failure"),
        "run_at": acceptance_summary.get("run_at"),
        "duration_ms": _safe_int(acceptance_summary.get("duration_ms")),
        "acceptance": {
            "passed": _safe_bool(acceptance_summary.get("passed")),
            "summary_line": acceptance_summary.get("summary_line"),
            "first_failure": acceptance_summary.get("first_failure"),
            "duration_ms": _safe_int(acceptance_summary.get("duration_ms")),
        },
        "regression": {},
    }
