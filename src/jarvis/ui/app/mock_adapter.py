"""App UI data adapter with API-first and mock fallback."""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib import request, error


API_ENDPOINTS = {
    "health": "/api/health",
    "capabilities": "/api/capabilities",
    "tasks": "/api/tasks",
    "approvals": "/api/approvals",
    "settings_effective": "/api/settings/effective",
    "skills": "/api/skills",
}


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


@dataclass
class AdapterResult:
    ok: bool
    data: Any
    source: str
    error: str = ""


class AppDataAdapter:
    """UI-safe adapter: tries HTTP API; falls back to local mock data shape."""

    def __init__(self, base_url: Optional[str] = None) -> None:
        self.base_url = (base_url or os.getenv("JARVIS_APP_API_BASE", "")).rstrip("/")
        self._mock_task_id = "task_mock_001"

    def _http_json(self, method: str, path: str, body: Optional[Dict[str, Any]] = None) -> AdapterResult:
        if not self.base_url:
            return AdapterResult(ok=False, data=None, source="mock", error="no_base_url")
        url = self.base_url + path
        req_body = None
        headers = {"Content-Type": "application/json"}
        if body is not None:
            req_body = json.dumps(body).encode("utf-8")
        req = request.Request(url=url, method=method, headers=headers, data=req_body)
        try:
            with request.urlopen(req, timeout=4) as resp:
                payload = resp.read().decode("utf-8", "ignore")
                data = json.loads(payload) if payload else {}
                return AdapterResult(ok=True, data=data, source="api")
        except (error.URLError, error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            return AdapterResult(ok=False, data=None, source="mock", error=type(exc).__name__)

    def _mock_health(self) -> Dict[str, Any]:
        return {
            "status": "ok",
            "gate_status": "PASSED",
            "mode": "safe",
            "run_status": "idle",
            "updated_at": _now(),
        }

    def _mock_capabilities(self) -> Dict[str, Any]:
        return {
            "tools": ["shell", "edit", "search", "test"],
            "modes": ["Safe", "Edit", "Review"],
            "provider": "mock",
        }

    def _mock_task(self, task_id: str) -> Dict[str, Any]:
        return {
            "task_id": task_id,
            "title": "Investigate flaky tests and patch safely",
            "status": "running",
            "project": "jarvis",
            "branch": "feature/ui-workspace",
            "created_at": _now(),
        }

    def _mock_events(self, task_id: str) -> List[Dict[str, Any]]:
        return [
            {"type": "task.created", "ts": _now(), "detail": {"task_id": task_id}},
            {"type": "plan.created", "ts": _now(), "detail": {"steps": 5}},
            {"type": "tool.called", "ts": _now(), "detail": {"tool": "shell", "cmd": "pytest -q"}},
            {"type": "rethink.started", "ts": _now(), "detail": {"reason": "low_confidence"}},
            {"type": "task.completed", "ts": _now(), "detail": {"status": "success"}},
        ]

    def _mock_replay(self, task_id: str) -> List[Dict[str, Any]]:
        events = self._mock_events(task_id)
        return [{"index": i + 1, **event} for i, event in enumerate(events)]

    def _mock_evidence(self, task_id: str) -> Dict[str, Any]:
        return {
            "task_id": task_id,
            "links": [
                "temp/gap_closure/final_report.json",
                "docs/benchmarks/final_comparable_report.md",
            ],
        }

    def _mock_operator_summary(self, task_id: str) -> Dict[str, Any]:
        return {
            "task_id": task_id,
            "changed_files": [
                "jarvis_desktop_app.py",
                "jarvis/cli.py",
            ],
            "diff_summary": "2 files changed, +120 -30",
            "tests_run": ["tests/ui -q", "tests/benchmark -q"],
            "risk_summary": "medium: edits + command execution",
            "rollback_available": True,
            "evidence_links": self._mock_evidence(task_id)["links"],
        }

    def _mock_approvals(self) -> List[Dict[str, Any]]:
        return [
            {
                "approval_id": "approval_mock_1",
                "risk_tier": "high",
                "reason": "Run edit-mode command touching project files",
                "status": "pending",
            }
        ]

    def _mock_settings_effective(self) -> Dict[str, Any]:
        return {
            "mode": "Safe",
            "hooks_enabled": True,
            "memory_enabled": True,
            "metrics_enabled": True,
            "source": "mock",
        }

    def _mock_skills(self) -> Dict[str, Any]:
        return {
            "skills": [
                {
                    "id": "repo-inspector",
                    "name": "Repo Inspector",
                    "status": "available",
                    "trust": "trusted",
                    "quarantine": False,
                    "source": "skills/repo-inspector",
                    "description": "Inspect project structure.",
                    "triggers": ["repo", "project", "structure"],
                }
            ],
            "count": 1,
            "roots": ["skills"],
        }

    def get_health(self) -> AdapterResult:
        res = self._http_json("GET", API_ENDPOINTS["health"])
        if res.ok:
            return res
        return AdapterResult(ok=True, data=self._mock_health(), source="mock")

    def get_capabilities(self) -> AdapterResult:
        res = self._http_json("GET", API_ENDPOINTS["capabilities"])
        if res.ok:
            return res
        return AdapterResult(ok=True, data=self._mock_capabilities(), source="mock")

    def create_task(self, prompt: str) -> AdapterResult:
        payload = {"prompt": prompt}
        res = self._http_json("POST", API_ENDPOINTS["tasks"], body=payload)
        if res.ok:
            return res
        task_id = f"task_{uuid.uuid4().hex[:8]}"
        self._mock_task_id = task_id
        return AdapterResult(ok=True, data={"task_id": task_id, "prompt": prompt}, source="mock")

    def get_task(self, task_id: str) -> AdapterResult:
        res = self._http_json("GET", f"{API_ENDPOINTS['tasks']}/{task_id}")
        if res.ok:
            return res
        return AdapterResult(ok=True, data=self._mock_task(task_id), source="mock")

    def get_task_events(self, task_id: str) -> AdapterResult:
        res = self._http_json("GET", f"{API_ENDPOINTS['tasks']}/{task_id}/events")
        if res.ok:
            return res
        return AdapterResult(ok=True, data=self._mock_events(task_id), source="mock")

    def get_task_replay(self, task_id: str) -> AdapterResult:
        res = self._http_json("GET", f"{API_ENDPOINTS['tasks']}/{task_id}/replay")
        if res.ok:
            return res
        return AdapterResult(ok=True, data=self._mock_replay(task_id), source="mock")

    def get_task_evidence(self, task_id: str) -> AdapterResult:
        res = self._http_json("GET", f"{API_ENDPOINTS['tasks']}/{task_id}/evidence")
        if res.ok:
            return res
        return AdapterResult(ok=True, data=self._mock_evidence(task_id), source="mock")

    def get_operator_summary(self, task_id: str) -> AdapterResult:
        res = self._http_json("GET", f"{API_ENDPOINTS['tasks']}/{task_id}/operator-summary")
        if res.ok:
            return res
        return AdapterResult(ok=True, data=self._mock_operator_summary(task_id), source="mock")

    def get_approvals(self) -> AdapterResult:
        res = self._http_json("GET", API_ENDPOINTS["approvals"])
        if res.ok:
            return res
        return AdapterResult(ok=True, data=self._mock_approvals(), source="mock")

    def approve(self, approval_id: str) -> AdapterResult:
        res = self._http_json("POST", f"{API_ENDPOINTS['approvals']}/{approval_id}/approve")
        if res.ok:
            return res
        return AdapterResult(ok=True, data={"approval_id": approval_id, "status": "approved"}, source="mock")

    def reject(self, approval_id: str) -> AdapterResult:
        res = self._http_json("POST", f"{API_ENDPOINTS['approvals']}/{approval_id}/reject")
        if res.ok:
            return res
        return AdapterResult(ok=True, data={"approval_id": approval_id, "status": "rejected"}, source="mock")

    def get_settings_effective(self) -> AdapterResult:
        res = self._http_json("GET", API_ENDPOINTS["settings_effective"])
        if res.ok:
            return res
        return AdapterResult(ok=True, data=self._mock_settings_effective(), source="mock")

    def get_skills(self) -> AdapterResult:
        res = self._http_json("GET", API_ENDPOINTS["skills"])
        if res.ok:
            return res
        return AdapterResult(ok=True, data=self._mock_skills(), source="mock")
