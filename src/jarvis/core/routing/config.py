"""Routing config loader / validator / reloader with safe fallbacks."""

from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter
from typing import Any

from ..result import error_result, ok_result


class RoutingConfigManager:
    def __init__(self, config_path: str | None = None) -> None:
        self.default_path = Path(__file__).with_name("default_routing_config.json")
        self.config_path = Path(config_path).resolve() if config_path else None
        self._config = self._load_default()
        self._source = str(self.default_path)
        if self.config_path:
            self.reload(self.config_path)

    @property
    def config(self) -> dict[str, Any]:
        return dict(self._config)

    @property
    def source(self) -> str:
        return self._source

    def reload(self, path: str | Path | None = None) -> dict:
        started = perf_counter()
        target = Path(path).resolve() if path else self.config_path
        if target is None:
            return ok_result({"config": self.config, "source": self._source, "reloaded": False}, started)
        if not target.exists():
            return error_result(
                "COMMON_NOT_FOUND",
                f"Routing config not found: {target}",
                {"path": str(target)},
                started,
            )
        parsed = self._parse_file(target)
        if not parsed["ok"]:
            return parsed
        validated = self.validate(parsed["data"])
        if not validated["ok"]:
            return validated
        self._config = validated["data"]["normalized"]
        self._source = str(target)
        self.config_path = target
        return ok_result({"config": self.config, "source": self._source, "reloaded": True}, started)

    def validate(self, config: dict[str, Any]) -> dict:
        started = perf_counter()
        if not isinstance(config, dict):
            return error_result("ROUTING_INVALID_INPUT", "routing config must be dict", {"type": str(type(config))}, started)
        normalized = self._load_default()
        warnings: list[dict[str, Any]] = []
        for key in ("domain_rules", "intent_rules", "policy_rules", "default_skills", "source_preferences", "approval_risk_config", "fallbacks"):
            value = config.get(key)
            if value is None:
                warnings.append({"kind": "schema", "field": key, "message": "missing, fallback to default"})
                continue
            if not isinstance(value, dict):
                warnings.append({"kind": "schema", "field": key, "message": "invalid type, fallback to default"})
                continue
            normalized[key] = value
        if "version" in config:
            normalized["version"] = str(config.get("version"))
        normalized.setdefault("fallbacks", {}).setdefault("low_confidence_threshold", 0.5)
        return ok_result({"normalized": normalized, "warnings": warnings, "schema_valid": len(warnings) == 0}, started)

    def validate_file(self, path: str | Path) -> dict:
        started = perf_counter()
        target = Path(path).resolve()
        parsed = self._parse_file(target)
        if not parsed["ok"]:
            return parsed
        validated = self.validate(parsed["data"])
        if not validated["ok"]:
            return validated
        return ok_result(
            {
                "path": str(target),
                "schema_valid": validated["data"]["schema_valid"],
                "warnings": validated["data"]["warnings"],
                "normalized": validated["data"]["normalized"],
            },
            started,
        )

    def run_drift_snapshot(self, samples: list[dict[str, Any]], route_callable) -> dict:
        started = perf_counter()
        snapshots: list[dict[str, Any]] = []
        for sample in samples:
            text = str(sample.get("input") or "")
            routed = route_callable(text)
            if not routed.get("ok"):
                snapshots.append({"input": text, "ok": False, "error": routed.get("error")})
                continue
            rr = routed["data"]["route_result"]
            snapshots.append(
                {
                    "input": text,
                    "ok": True,
                    "domain": rr.get("domain"),
                    "intent": rr.get("intent"),
                    "confidence": rr.get("confidence"),
                    "fallback_used": rr.get("fallback_used"),
                }
            )
        return ok_result({"samples": snapshots, "count": len(snapshots)}, started)

    def _load_default(self) -> dict[str, Any]:
        return json.loads(self.default_path.read_text(encoding="utf-8"))

    def _parse_file(self, path: Path) -> dict:
        started = perf_counter()
        raw = path.read_text(encoding="utf-8")
        try:
            return ok_result(json.loads(raw), started)
        except Exception:
            pass
        # Optional YAML support when pyyaml exists.
        try:
            import yaml  # type: ignore

            loaded = yaml.safe_load(raw)
            if not isinstance(loaded, dict):
                return error_result("ROUTING_INVALID_INPUT", "yaml config must load to dict", {"path": str(path)}, started)
            return ok_result(loaded, started)
        except Exception as exc:
            return error_result(
                "ROUTING_INVALID_INPUT",
                "failed to parse routing config as JSON/YAML",
                {"path": str(path), "exception": str(exc)},
                started,
            )
