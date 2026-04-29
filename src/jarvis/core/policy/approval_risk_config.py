from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ApprovalRiskConfigSnapshot:
    version: str
    source: str
    config: dict[str, Any]


class ApprovalRiskConfigManager:
    def __init__(self, config_path: str | None = None) -> None:
        self.default_path = Path(__file__).with_name("default_approval_risk_config.json")
        self.config_path = Path(config_path).resolve() if config_path else self.default_path
        self._history: list[ApprovalRiskConfigSnapshot] = []
        self._active = self._load(self.config_path)
        self._history.append(self._active)

    @property
    def active(self) -> dict[str, Any]:
        return dict(self._active.config)

    @property
    def version(self) -> str:
        return self._active.version

    def load(self, path: str | Path | None = None) -> dict[str, Any]:
        target = Path(path).resolve() if path else self.config_path
        snap = self._load(target)
        self._active = snap
        self._history.append(snap)
        self.config_path = target
        return {"ok": True, "data": {"version": snap.version, "source": snap.source, "config": snap.config}}

    def rollback(self) -> dict[str, Any]:
        if len(self._history) < 2:
            return {"ok": False, "error": {"code": "POLICY_ROLLBACK_UNAVAILABLE", "message": "no prior snapshot"}}
        self._history.pop()
        self._active = self._history[-1]
        return {"ok": True, "data": {"version": self._active.version, "source": self._active.source}}

    def validate(self, payload: dict[str, Any]) -> dict[str, Any]:
        required = {"version", "default_tier", "tiers", "action_category_map", "matrix"}
        missing = sorted(required - set(payload.keys()))
        if missing:
            return {"ok": False, "error": {"code": "POLICY_CONFIG_INVALID", "message": f"missing keys: {missing}"}}
        if payload["default_tier"] not in payload["tiers"]:
            return {"ok": False, "error": {"code": "POLICY_CONFIG_INVALID", "message": "default_tier not in tiers"}}
        return {"ok": True, "data": {"valid": True}}

    def _load(self, path: Path) -> ApprovalRiskConfigSnapshot:
        raw = json.loads(path.read_text(encoding="utf-8"))
        valid = self.validate(raw)
        if not valid.get("ok"):
            raise ValueError(valid["error"]["message"])
        return ApprovalRiskConfigSnapshot(version=str(raw.get("version") or "unknown"), source=str(path), config=raw)

