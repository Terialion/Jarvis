from __future__ import annotations

import hashlib
import json
import os
import shutil
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .loader import SkillLoader
from .quarantine import SkillQuarantineStatus
from .sources import SkillSource
from .trust import SkillTrustStatus
from .validator import SkillValidator, default_validation_mode_for_spec
from ..agent.types import redact_secret_text


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _redact_jsonish(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _redact_jsonish(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_jsonish(item) for item in value]
    if isinstance(value, str):
        return redact_secret_text(value)
    return value


@dataclass
class SkillEnabledState:
    name: str
    enabled: bool
    reason: str | None = None
    updated_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SkillInstallRecord:
    name: str
    source: str
    installed_path: str
    hash: str
    installed_at: str
    validation_mode: str
    validation_status: str
    enabled: bool
    trust_status: str
    quarantine_status: str
    version: str | None = None
    source_ref: str | None = None
    old_hash: str | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SkillLifecycleStore:
    def __init__(self, *, project_root: str | Path = ".", config_path: str | Path | None = None) -> None:
        self.project_root = Path(project_root).resolve()
        raw_path = config_path or os.getenv("JARVIS_SKILL_CONFIG_PATH") or (self.project_root / ".jarvis" / "skills" / "config.json")
        self.config_path = Path(raw_path).resolve()
        self.last_error: dict[str, Any] | None = None

    def default_config(self) -> dict[str, Any]:
        return {
            "version": 1,
            "sources": [],
            "installed": {},
            "enabled": {},
            "trust": {},
            "quarantine": {},
        }

    def load(self) -> dict[str, Any]:
        self.last_error = None
        if not self.config_path.exists():
            config = self.default_config()
            self.save(config)
            return config
        try:
            raw = json.loads(self.config_path.read_text(encoding="utf-8"))
        except Exception as exc:
            self.last_error = {
                "code": "corrupted_lifecycle_config",
                "path": str(self.config_path),
                "error": type(exc).__name__,
            }
            return self.default_config()
        if not isinstance(raw, dict):
            self.last_error = {
                "code": "corrupted_lifecycle_config",
                "path": str(self.config_path),
                "error": "invalid_root_type",
            }
            return self.default_config()
        config = self.default_config()
        for key in config:
            value = raw.get(key, config[key])
            config[key] = value if isinstance(value, type(config[key])) else config[key]
        return config

    def save(self, config: dict[str, Any]) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        redacted = _redact_jsonish(config)
        self.config_path.write_text(json.dumps(redacted, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    def list_sources(self) -> list[SkillSource]:
        config = self.load()
        rows = []
        for row in list(config.get("sources") or []):
            if not isinstance(row, dict):
                continue
            rows.append(
                SkillSource(
                    name=str(row.get("name") or ""),
                    kind=str(row.get("kind") or "local"),
                    uri_or_path=str(row.get("uri_or_path") or ""),
                    enabled=bool(row.get("enabled", True)),
                    priority=int(row.get("priority") or 50),
                    added_at=str(row.get("added_at") or _utc_now()),
                )
            )
        return rows

    def add_source(self, name: str, path_or_uri: str, *, kind: str = "local", priority: int = 50) -> SkillSource:
        config = self.load()
        kept = [row for row in list(config.get("sources") or []) if str((row or {}).get("name") or "") != name]
        source = SkillSource(name=name, kind=kind, uri_or_path=path_or_uri, enabled=True, priority=priority)
        kept.append(source.to_dict())
        config["sources"] = sorted(kept, key=lambda row: (-int((row or {}).get("priority") or 0), str((row or {}).get("name") or "").lower()))
        self.save(config)
        return source

    def remove_source(self, name: str) -> bool:
        config = self.load()
        before = len(list(config.get("sources") or []))
        config["sources"] = [row for row in list(config.get("sources") or []) if str((row or {}).get("name") or "") != name]
        changed = len(config["sources"]) != before
        if changed:
            self.save(config)
        return changed


class SkillLifecycleManager:
    def __init__(
        self,
        *,
        project_root: str | Path = ".",
        install_root: str | Path | None = None,
        config_path: str | Path | None = None,
        loader: SkillLoader | None = None,
        validator: SkillValidator | None = None,
        store: SkillLifecycleStore | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.install_root = Path(install_root or (self.project_root / ".jarvis" / "skills")).resolve()
        self.loader = loader or SkillLoader()
        self.validator = validator or SkillValidator()
        self.store = store or SkillLifecycleStore(project_root=self.project_root, config_path=config_path)

    def current_config(self) -> dict[str, Any]:
        return self.store.load()

    def lifecycle_error(self) -> dict[str, Any] | None:
        self.store.load()
        return self.store.last_error

    def install_skill(self, source: str, *, mode: str = "auto", enabled: bool = False) -> dict[str, Any]:
        resolved = self._resolve_install_source(source)
        if not resolved["ok"]:
            return resolved
        source_dir = Path(str(resolved["skill_dir"])).resolve()
        source_ref = str(resolved["source_ref"])
        source_kind = str(resolved["source_kind"])
        spec = self.loader.parse_skill_dir(source_dir, source="user" if source_kind == "jarvis" else "extra")
        validation_mode = self._pick_validation_mode(spec.path, mode=mode, source_kind=source_kind)
        validation = self.validator.validate_spec(spec, mode=validation_mode)
        warnings = [finding.message for finding in validation.findings if finding.level == "warning"]
        errors = [finding.message for finding in validation.findings if finding.level == "error"]
        target_dir = self.install_root / spec.name
        if target_dir.exists():
            shutil.rmtree(target_dir)
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        self._copy_skill_dir(source_dir, target_dir)
        spec = self.loader.parse_skill_dir(target_dir, source="user")
        install_hash = compute_skill_hash(target_dir)
        record = SkillInstallRecord(
            name=spec.name,
            source=source_kind,
            installed_path=str(target_dir),
            hash=install_hash,
            installed_at=_utc_now(),
            validation_mode=validation_mode,
            validation_status="ok" if validation.ok else "error",
            enabled=bool(enabled and validation.ok),
            trust_status="unknown" if source_kind != "builtin" else "trusted",
            quarantine_status="clear",
            version=str(spec.metadata.get("version") or "") or None,
            source_ref=source_ref,
            warnings=warnings,
            errors=errors,
        )
        config = self.store.load()
        config.setdefault("installed", {})[spec.name] = record.to_dict()
        config.setdefault("enabled", {})[spec.name] = bool(record.enabled)
        config.setdefault("trust", {})[spec.name] = record.trust_status
        config.setdefault("quarantine", {})[spec.name] = SkillQuarantineStatus(name=spec.name).to_dict()
        self.store.save(config)
        return {
            "ok": validation.ok,
            "status": "installed" if validation.ok else "validation_failed",
            "record": record.to_dict(),
            "validation": validation.to_dict(),
        }

    def update_skill(self, name: str) -> dict[str, Any]:
        config = self.store.load()
        record = dict((config.get("installed") or {}).get(name) or {})
        if not record:
            return {"ok": False, "error": "skill_not_installed", "skill_name": name}
        source_ref = str(record.get("source_ref") or "").strip()
        if not source_ref:
            return {"ok": False, "error": "update_source_missing", "skill_name": name}
        old_hash = str(record.get("hash") or "")
        result = self.install_skill(source_ref, mode=str(record.get("validation_mode") or "auto"), enabled=bool((config.get("enabled") or {}).get(name, False)))
        if not result.get("ok"):
            return {"ok": False, "error": "update_validation_failed", "skill_name": name, "previous_record": record, "update": result}
        updated_record = dict(result.get("record") or {})
        updated_record["old_hash"] = old_hash
        config = self.store.load()
        config.setdefault("installed", {})[name] = updated_record
        self.store.save(config)
        return {"ok": True, "status": "updated", "record": updated_record, "old_hash": old_hash, "new_hash": updated_record.get("hash")}

    def set_enabled(self, name: str, enabled: bool, *, reason: str | None = None) -> dict[str, Any]:
        config = self.store.load()
        quarantine = dict((config.get("quarantine") or {}).get(name) or {})
        if bool(quarantine.get("quarantined")) and enabled:
            return {"ok": False, "error": "skill_quarantined", "skill_name": name}
        install = dict((config.get("installed") or {}).get(name) or {})
        validation_status = str(install.get("validation_status") or "")
        if enabled and validation_status == "error":
            return {"ok": False, "error": "validation_failed", "skill_name": name}
        state = SkillEnabledState(name=name, enabled=enabled, reason=reason)
        config.setdefault("enabled", {})[name] = enabled
        if install:
            install["enabled"] = enabled
            config.setdefault("installed", {})[name] = install
        self.store.save(config)
        return {"ok": True, "state": state.to_dict()}

    def trust_skill(self, name: str, *, trusted: bool = True, reason: str | None = None) -> dict[str, Any]:
        config = self.store.load()
        status = SkillTrustStatus(name=name, status="trusted" if trusted else "untrusted", reason=reason)
        config.setdefault("trust", {})[name] = status.status
        install = dict((config.get("installed") or {}).get(name) or {})
        if install:
            install["trust_status"] = status.status
            config.setdefault("installed", {})[name] = install
        self.store.save(config)
        return {"ok": True, "trust": status.to_dict()}

    def quarantine_skill(self, name: str, *, quarantined: bool = True, reason: str | None = None, findings: list[str] | None = None) -> dict[str, Any]:
        config = self.store.load()
        status = SkillQuarantineStatus(name=name, quarantined=quarantined, reason=reason, scanner_findings=list(findings or []))
        config.setdefault("quarantine", {})[name] = status.to_dict()
        if quarantined:
            config.setdefault("enabled", {})[name] = False
        install = dict((config.get("installed") or {}).get(name) or {})
        if install:
            install["quarantine_status"] = "quarantined" if quarantined else "clear"
            install["enabled"] = False if quarantined else bool((config.get("enabled") or {}).get(name, False))
            config.setdefault("installed", {})[name] = install
        self.store.save(config)
        return {"ok": True, "quarantine": status.to_dict()}

    def check_skill(self, spec: Any, *, duplicate_status: str = "primary") -> dict[str, Any]:
        config = self.store.load()
        install = dict((config.get("installed") or {}).get(spec.name) or {})
        validation_mode = str(install.get("validation_mode") or default_validation_mode_for_spec(spec))
        validation = self.validator.validate_spec(spec, mode=validation_mode)
        enabled = bool((config.get("enabled") or {}).get(spec.name, install.get("enabled", self._default_enabled_for_source(spec.source))))
        trust_status = str((config.get("trust") or {}).get(spec.name, install.get("trust_status", self._default_trust_for_source(spec.source))))
        quarantine = dict((config.get("quarantine") or {}).get(spec.name) or {})
        quarantined = bool(quarantine.get("quarantined"))
        deps = self._check_requires(spec)
        return {
            "name": spec.name,
            "source": spec.source,
            "path": spec.path,
            "hash": compute_skill_hash(str(install.get("installed_path") or spec.path)),
            "version": str(spec.metadata.get("version") or install.get("version") or "") or None,
            "enabled": enabled and not quarantined,
            "trust_status": trust_status,
            "quarantine_status": "quarantined" if quarantined else "clear",
            "validation_mode": validation_mode,
            "validation_status": "ok" if validation.ok else "error",
            "validator_errors": [finding.message for finding in validation.findings if finding.level == "error"],
            "validator_warnings": [finding.message for finding in validation.findings if finding.level == "warning"],
            "duplicate_status": duplicate_status,
            "loadable": enabled and not quarantined and validation.ok,
            "executable": enabled and not quarantined and validation.ok,
            "risk_level": spec.risk_level,
            "allowed_tools": list(spec.allowed_tools),
            "installed": bool(install),
            "installed_path": str(install.get("installed_path") or spec.path),
            "source_ref": install.get("source_ref"),
            "lifecycle_config_error": self.store.last_error,
            "dependency_warnings": deps.get("warnings", []),
            "missing_bins": deps.get("missing_bins", []),
            "missing_env": deps.get("missing_env", []),
        }

    def lifecycle_state_for(self, spec: Any) -> dict[str, Any]:
        config = self.store.load()
        return self._lifecycle_state(spec, config)

    def lifecycle_state_batch(self, specs: list[Any]) -> list[dict[str, Any]]:
        """Load config once and compute lifecycle state for all specs."""
        config = self.store.load()
        return [self._lifecycle_state(s, config) for s in specs]

    def _lifecycle_state(self, spec: Any, config: dict[str, Any]) -> dict[str, Any]:
        install = dict((config.get("installed") or {}).get(spec.name) or {})
        enabled = bool((config.get("enabled") or {}).get(spec.name, install.get("enabled", self._default_enabled_for_source(spec.source))))
        trust_status = str((config.get("trust") or {}).get(spec.name, install.get("trust_status", self._default_trust_for_source(spec.source))))
        quarantine = dict((config.get("quarantine") or {}).get(spec.name) or {})
        quarantined = bool(quarantine.get("quarantined"))
        validation_status = str(install.get("validation_status") or "ok")
        deps = self._check_requires(spec)
        return {
            "installed": bool(install),
            "enabled": enabled and not quarantined,
            "requested_enabled": enabled,
            "trust_status": trust_status,
            "quarantined": quarantined,
            "quarantine_reason": str(quarantine.get("reason") or "") or None,
            "validation_status": validation_status,
            "validation_mode": str(install.get("validation_mode") or default_validation_mode_for_spec(spec)),
            "hash": str(install.get("hash") or ""),
            "installed_path": str(install.get("installed_path") or spec.path),
            "source_ref": str(install.get("source_ref") or "") or None,
            "dependency_warnings": deps.get("warnings", []),
            "missing_bins": deps.get("missing_bins", []),
            "missing_env": deps.get("missing_env", []),
        }

    @staticmethod
    def _check_requires(spec: Any) -> dict[str, Any]:
        """Check skill dependency declarations (bins/env) and return warnings only.

        Conservative: missing deps produce warnings, never disable the skill.
        Matches OpenClaw's requires.bins / requires.anyBins semantics.
        """
        requires = spec.metadata.get("requires") if hasattr(spec, "metadata") else None
        if not isinstance(requires, dict):
            return {}

        bins = requires.get("bins")
        any_bins = requires.get("anyBins")
        env_vars = requires.get("env")

        missing_bins: list[str] = []
        missing_any_bins: list[str] = []
        missing_env: list[str] = []

        if isinstance(bins, list):
            for b in bins:
                if isinstance(b, str) and not shutil.which(b):
                    missing_bins.append(b)

        if isinstance(any_bins, list):
            found = any(isinstance(b, str) and shutil.which(b) for b in any_bins)
            if not found and any_bins:
                missing_any_bins = [str(b) for b in any_bins if isinstance(b, str)]

        if isinstance(env_vars, list):
            for e in env_vars:
                if isinstance(e, str) and not os.environ.get(e):
                    missing_env.append(e)

        warnings: list[str] = []
        for b in missing_bins:
            warnings.append(f"required binary not found on PATH: {b}")
        if missing_any_bins:
            warnings.append(f"none of the optional binaries found on PATH: {', '.join(missing_any_bins)}")
        for e in missing_env:
            warnings.append(f"required env var not set: {e}")

        return {
            "missing_bins": missing_bins,
            "missing_any_bins": missing_any_bins,
            "missing_env": missing_env,
            "warnings": warnings,
        }

    @staticmethod
    def _default_enabled_for_source(source: str) -> bool:
        return True

    @staticmethod
    def _default_trust_for_source(source: str) -> str:
        return "trusted" if str(source) == "builtin" else "unknown"

    def _pick_validation_mode(self, path: str, *, mode: str, source_kind: str) -> str:
        if mode in {"strict", "compatibility"}:
            return mode
        if source_kind == "jarvis":
            return "strict"
        path_obj = Path(path).resolve()
        if str(path_obj).startswith(str((self.project_root / ".jarvis" / "skills").resolve())):
            return "strict"
        return "compatibility"

    def _resolve_install_source(self, source: str) -> dict[str, Any]:
        raw = Path(source).expanduser()
        if not raw.exists():
            return {"ok": False, "error": "source_not_found", "source": source}
        if raw.is_file() and raw.suffix.lower() == ".md" and raw.name.upper() == "SKILL.MD":
            return {"ok": True, "skill_dir": str(raw.parent.resolve()), "source_ref": str(raw.resolve()), "source_kind": "jarvis" if self._is_jarvis_authored(raw.parent) else "imported"}
        if raw.is_dir() and (raw / "SKILL.md").exists():
            return {"ok": True, "skill_dir": str(raw.resolve()), "source_ref": str(raw.resolve()), "source_kind": "jarvis" if self._is_jarvis_authored(raw) else "imported"}
        if raw.is_file() and raw.suffix.lower() in {".zip", ".skill"}:
            temp_dir = self.install_root.parent / ".tmp_install_extract" / raw.stem
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
            temp_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(raw) as archive:
                archive.extractall(temp_dir)
            skill_dir = next((candidate for candidate in [temp_dir, *temp_dir.iterdir()] if candidate.is_dir() and (candidate / "SKILL.md").exists()), None)
            if skill_dir is None:
                return {"ok": False, "error": "skill_md_not_found_in_archive", "source": source}
            return {"ok": True, "skill_dir": str(skill_dir.resolve()), "source_ref": str(raw.resolve()), "source_kind": "imported"}
        return {"ok": False, "error": "unsupported_source", "source": source}

    def _copy_skill_dir(self, source_dir: Path, target_dir: Path) -> None:
        shutil.copytree(source_dir, target_dir, dirs_exist_ok=True)

    def _is_jarvis_authored(self, path: Path) -> bool:
        lowered = str(path.resolve()).replace("\\", "/").lower()
        return "/.jarvis/skills/" in lowered or lowered.endswith("/.jarvis/skills")


def compute_skill_hash(skill_dir: str | Path) -> str:
    root = Path(skill_dir).resolve()
    digest = hashlib.sha256()
    if not root.exists():
        return "sha256:"
    for candidate in sorted(path for path in root.rglob("*") if path.is_file()):
        digest.update(str(candidate.relative_to(root)).replace("\\", "/").encode("utf-8"))
        digest.update(candidate.read_bytes())
    return f"sha256:{digest.hexdigest()}"
