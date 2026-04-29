"""Skill loader for bundled/local/override sources."""

from __future__ import annotations

import json
import re
from pathlib import Path
from time import perf_counter
from typing import Any

from ..result import error_result, ok_result
from .models import SkillRecord


_DEFAULT_BUNDLED = [
    {
        "skill_id": "skill.repo_fix",
        "skill_name": "Repo Fix",
        "source": "bundled",
        "required_tools": ["repo_reader", "file_editor", "test_runner"],
        "tags": ["bugfix", "python", "repo"],
        "description": "Search code, patch minimal lines, and run tests.",
        "priority_hint": 0.9,
    },
    {
        "skill_id": "skill.command_verify",
        "skill_name": "Command Verify",
        "source": "bundled",
        "required_tools": ["command_runner"],
        "tags": ["command", "verify"],
        "description": "Run command probes and parse outcomes.",
        "priority_hint": 0.4,
    },
]


class SkillLoader:
    SKILL_MARKERS = (
        "SKILL.md",
        "skill.md",
        "manifest.json",
        "skill.json",
        "skill.yaml",
        "skill.yml",
        "README.md",
    )

    ROOT_CANDIDATES = (
        "skills",
        ".skill",
        "jarvis/skills",
        "src/jarvis/skills",
        "openclaw/skills",
        "OpenClaw/skills",
    )

    ROOT_PRIORITY = {
        "skills": 100,
        ".skill": 95,
        "jarvis/skills": 90,
        "src/jarvis/skills": 80,
        "openclaw/skills": 50,
        "OpenClaw/skills": 50,
    }

    def __init__(self, available_tools: list[str] | None = None) -> None:
        self.available_tools = set(available_tools or [])

    def load_bundled_skills(self) -> dict:
        started = perf_counter()
        validated, filtered = self._validate_and_gate(_DEFAULT_BUNDLED, source="bundled")
        return ok_result(
            {
                "source": "bundled",
                "loaded_skills": validated,
                "filtered_skills": filtered,
            },
            started,
        )

    def load_local_skills(self, project_root: str) -> dict:
        started = perf_counter()
        root = Path(project_root).resolve()
        if not root.exists() or not root.is_dir():
            return error_result(
                "REPO_INVALID_ROOT",
                f"Invalid project root: {project_root}",
                {"project_root": project_root},
                started,
            )
        discovery = self.discover_skill_records(root)
        entries = [self._record_to_entry(record) for record in discovery["records"] if record.status != "invalid"]
        validated, filtered = self._validate_and_gate(entries, source="local")
        return ok_result(
            {
                "source": "local",
                "loaded_skills": validated,
                "filtered_skills": filtered,
                "discovery_warnings": discovery["warnings"],
            },
            started,
        )

    def load_override_skills(self, overrides: list[dict] | None = None) -> dict:
        started = perf_counter()
        validated, filtered = self._validate_and_gate(list(overrides or []), source="override")
        return ok_result(
            {
                "source": "override",
                "loaded_skills": validated,
                "filtered_skills": filtered,
            },
            started,
        )

    def validate_skill(self, skill_entry: dict) -> dict:
        started = perf_counter()
        validated, filtered = self._validate_and_gate([skill_entry], source=str(skill_entry.get("source") or "unknown"))
        if validated:
            return ok_result(validated[0], started)
        return error_result(
            "SKILL_INVALID_ENTRY",
            "Skill validation failed",
            {"filtered": filtered},
            started,
        )

    def discover_skill_roots(self, project_root: str | Path | None = None) -> list[Path]:
        root = Path(project_root or ".").resolve()
        discovered: list[Path] = []
        for rel in self.ROOT_CANDIDATES:
            candidate = (root / rel).resolve()
            if candidate.exists() and candidate.is_dir():
                discovered.append(candidate)
        return discovered

    def discover_skill_records(self, project_root: str | Path | None = None) -> dict:
        roots = self.discover_skill_roots(project_root)
        warnings: list[str] = []
        winners: dict[str, SkillRecord] = {}
        shadowed_records: list[SkillRecord] = []
        root_priority: dict[str, int] = {}
        seen_roots: set[str] = set()

        for root in roots:
            root_key = self._detect_root_key(root, project_root)
            root_pri = int(self.ROOT_PRIORITY.get(root_key, 10))
            root_priority[str(root)] = root_pri
            for item in sorted(root.iterdir(), key=lambda p: p.name.lower()):
                if not item.is_dir():
                    continue
                marker_paths = [item / marker for marker in self.SKILL_MARKERS if (item / marker).exists()]
                if not marker_paths:
                    continue
                record = self._build_skill_record(item, marker_paths, root, root_priority=root_pri)
                normalized_id = self._normalize_skill_id(record.id or item.name)
                record.id = normalized_id
                if str(item.resolve()).lower() in seen_roots:
                    continue
                seen_roots.add(str(item.resolve()).lower())
                existing = winners.get(normalized_id)
                if existing is None:
                    winners[normalized_id] = record
                    continue
                if record.source_priority > existing.source_priority:
                    old = SkillRecord(**existing.to_dict())
                    old.status = "shadowed"
                    old.shadowed_by = record.id
                    old.metadata = {**old.metadata, "shadowed_by_source": record.source, "shadowed_by_root": record.root}
                    shadowed_records.append(old)
                    winners[normalized_id] = record
                    warnings.append(f"duplicate_skill_id_shadowed:{normalized_id}")
                else:
                    loser = SkillRecord(**record.to_dict())
                    loser.status = "shadowed"
                    loser.shadowed_by = existing.id
                    loser.metadata = {**loser.metadata, "shadowed_by_source": existing.source, "shadowed_by_root": existing.root}
                    shadowed_records.append(loser)
                    warnings.append(f"duplicate_skill_id_shadowed:{normalized_id}")

        return {
            "roots": [str(path) for path in roots],
            "records": list(winners.values()),
            "shadowed_records": shadowed_records,
            "root_priority": root_priority,
            "warnings": warnings,
        }

    def load_skill_body(self, record: SkillRecord, *, max_bytes: int = 32768) -> tuple[str, bool]:
        path: Path | None = None
        if record.skill_md_path:
            path = Path(record.skill_md_path)
        elif record.manifest_path:
            path = Path(record.manifest_path)
        if path is None or not path.exists():
            return "", False
        try:
            data = path.read_bytes()[:max_bytes]
            return data.decode("utf-8", errors="replace"), True
        except Exception:
            return "", False

    def _validate_and_gate(self, entries: list[dict], source: str) -> tuple[list[dict], list[dict]]:
        loaded: list[dict] = []
        filtered: list[dict] = []
        for raw in entries:
            ok, reason, normalized = self._normalize_entry(raw, source=source)
            if not ok:
                filtered.append({"skill_entry": raw, "reason": reason, "filter_type": "validation"})
                continue
            missing = sorted(set(normalized["required_tools"]) - self.available_tools) if self.available_tools else []
            if missing:
                filtered.append(
                    {
                        "skill_id": normalized["skill_id"],
                        "reason": "required_tools_unavailable",
                        "missing_tools": missing,
                        "filter_type": "tool_availability_gating",
                    }
                )
                continue
            loaded.append(normalized)
        return loaded, filtered

    @staticmethod
    def _normalize_entry(raw: dict, source: str) -> tuple[bool, str, dict]:
        if not isinstance(raw, dict):
            return False, "entry_not_dict", {}
        skill_id = str(raw.get("skill_id") or "").strip()
        skill_name = str(raw.get("skill_name") or "").strip()
        if not skill_id or not skill_name:
            return False, "missing_skill_id_or_name", {}
        required_tools = [str(v).strip() for v in list(raw.get("required_tools") or []) if str(v).strip()]
        tags = [str(v).strip() for v in list(raw.get("tags") or []) if str(v).strip()]
        return (
            True,
            "",
            {
                "skill_id": skill_id,
                "skill_name": skill_name,
                "source": str(raw.get("source") or source),
                "status": str(raw.get("status") or "enabled"),
                "required_tools": required_tools,
                "tags": tags,
                "description": str(raw.get("description") or "").strip(),
                "priority_hint": float(raw.get("priority_hint") or 0.0),
                "metadata": dict(raw.get("metadata") or {}),
                "permissions": [str(v).strip() for v in list(raw.get("permissions") or []) if str(v).strip()],
            },
        )

    def _build_skill_record(self, skill_dir: Path, marker_paths: list[Path], root: Path, *, root_priority: int) -> SkillRecord:
        manifest_path = self._pick_manifest(marker_paths)
        md_path = self._pick_markdown(marker_paths)
        parsed: dict = {}
        errors: list[str] = []
        if manifest_path:
            parsed, parse_errors = self._parse_manifest(manifest_path)
            errors.extend(parse_errors)
        if (not parsed or parsed.get("_partial")) and md_path:
            md_parsed, parse_errors = self._parse_markdown(md_path)
            errors.extend(parse_errors)
            parsed = {**md_parsed, **parsed}

        skill_name = str(parsed.get("name") or parsed.get("skill_name") or skill_dir.name).strip()
        skill_id = str(parsed.get("id") or parsed.get("skill_id") or skill_dir.name).strip()
        description = str(parsed.get("description") or "").strip()
        triggers = self._ensure_list(parsed.get("triggers"))
        when_to_use = self._ensure_list(parsed.get("when_to_use"))
        if not triggers and when_to_use:
            triggers = list(when_to_use)
        tools = self._ensure_list(parsed.get("tools") or parsed.get("required_tools"))
        permissions = self._ensure_list(parsed.get("permissions"))
        allowed_tools = self._ensure_list(parsed.get("allowed-tools") or parsed.get("allowed_tools"))
        arguments = self._ensure_list(parsed.get("arguments") or parsed.get("argument-hint") or parsed.get("argument_hint"))
        invocation = str(parsed.get("invocation") or "auto").strip().lower()
        if invocation not in {"auto", "manual", "disabled"}:
            invocation = "auto"
        source = self._detect_source(skill_dir, root)
        trust_raw = str(parsed.get("trust") or parsed.get("trust_level") or "").strip().lower()
        trust = trust_raw or self._default_trust_for_source(source)
        entrypoint = parsed.get("entrypoint")
        dynamic_context = self._to_bool(parsed.get("dynamic_context") or parsed.get("dynamic-context"))
        subagent = self._to_bool(parsed.get("subagent"))

        status = "available"
        quarantine = False
        if errors:
            status = "invalid"
        if invocation == "disabled":
            status = "disabled"
        if trust in {"untrusted", "unknown", "needs_review"}:
            quarantine = True
        if any(permission in {"shell.exec_all", "filesystem.write_all", "network.unrestricted"} for permission in permissions):
            quarantine = True
        if status != "invalid" and quarantine:
            status = "quarantined"
        if status == "disabled":
            quarantine = True

        return SkillRecord(
            id=self._normalize_skill_id(skill_id),
            name=skill_name,
            root=str(skill_dir.resolve()),
            source=source,
            description=description,
            entrypoint=str(entrypoint).strip() if entrypoint else None,
            triggers=triggers,
            tools=tools,
            permissions=permissions,
            trust=trust or "untrusted",
            quarantine=quarantine,
            status=status,
            manifest_path=str(manifest_path.resolve()) if manifest_path else None,
            skill_md_path=str(md_path.resolve()) if md_path else None,
            when_to_use=when_to_use,
            invocation=invocation,
            allowed_tools=allowed_tools,
            arguments=arguments,
            dynamic_context=dynamic_context,
            subagent=subagent,
            source_priority=root_priority,
            shadowed_by=None,
            body_loaded=False,
            errors=errors,
            metadata={
                "marker_files": [path.name for path in marker_paths],
                "body_path": str((md_path or manifest_path).resolve()) if (md_path or manifest_path) else "",
            },
        )

    @staticmethod
    def _detect_source(skill_dir: Path, root: Path) -> str:
        low = str(skill_dir).replace("\\", "/").lower()
        if "/openclaw/skills/" in low:
            return "openclaw_reference"
        if "/openclaw/" in low:
            return "imported_reference"
        if "/claude-code/" in low:
            return "imported_reference"
        if "plugin" in low or ".system" in low or "/cache/" in low:
            return "plugin"
        if root.name.lower() == "skills":
            return "local"
        return "local"

    @staticmethod
    def _default_trust_for_source(source: str) -> str:
        if source in {"local", "bundled", "builtin"}:
            return "trusted"
        if source in {"openclaw_reference", "imported_reference"}:
            return "imported-reference"
        return "untrusted"

    def _detect_root_key(self, root: Path, project_root: str | Path | None) -> str:
        base = Path(project_root or ".").resolve()
        try:
            rel = root.resolve().relative_to(base).as_posix()
            return rel
        except Exception:
            return root.name

    @staticmethod
    def _pick_manifest(marker_paths: list[Path]) -> Path | None:
        for name in ("manifest.json", "skill.json", "skill.yaml", "skill.yml"):
            for path in marker_paths:
                if path.name == name:
                    return path
        return None

    @staticmethod
    def _pick_markdown(marker_paths: list[Path]) -> Path | None:
        for name in ("SKILL.md", "skill.md", "README.md"):
            for path in marker_paths:
                if path.name == name:
                    return path
        return None

    @staticmethod
    def _to_bool(value: object) -> bool:
        if isinstance(value, bool):
            return value
        text = str(value or "").strip().lower()
        return text in {"1", "true", "yes", "on"}

    @staticmethod
    def _ensure_list(value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [part.strip() for part in re.split(r"[,\n]", value) if part.strip()]
        if isinstance(value, list):
            out: list[str] = []
            for item in value:
                text = str(item).strip()
                if text:
                    out.append(text)
            return out
        return [str(value).strip()] if str(value).strip() else []

    @staticmethod
    def _normalize_skill_id(raw: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9_.-]+", "-", (raw or "").strip().lower())
        normalized = normalized.strip("-._")
        return normalized or "unknown-skill"

    def _parse_manifest(self, path: Path) -> tuple[dict, list[str]]:
        text = path.read_text(encoding="utf-8", errors="replace")
        if path.suffix.lower() == ".json":
            try:
                payload = json.loads(text)
                if isinstance(payload, dict):
                    return payload, []
                return {}, [f"manifest_not_object:{path.name}"]
            except json.JSONDecodeError as exc:
                return {}, [f"manifest_json_error:{exc.msg}"]
        return self._parse_simple_yaml(text)

    def _parse_simple_yaml(self, text: str) -> tuple[dict, list[str]]:
        data: dict[str, object] = {}
        errors: list[str] = []
        current_list_key: str | None = None
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("- ") and current_list_key:
                data.setdefault(current_list_key, [])
                assert isinstance(data[current_list_key], list)
                data[current_list_key].append(line[2:].strip())
                continue
            if ":" not in line:
                current_list_key = None
                continue
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if not key:
                continue
            if not value:
                current_list_key = key
                data[key] = []
            elif value.startswith("[") and value.endswith("]"):
                items = [item.strip().strip("'\"") for item in value[1:-1].split(",") if item.strip()]
                data[key] = items
                current_list_key = None
            else:
                data[key] = value.strip("'\"")
                current_list_key = None
        if not data:
            errors.append("manifest_yaml_empty")
        return data, errors

    def _parse_markdown(self, path: Path) -> tuple[dict, list[str]]:
        text = path.read_text(encoding="utf-8", errors="replace")
        data: dict[str, object] = {}
        errors: list[str] = []
        lines = text.splitlines()
        if lines and lines[0].strip() == "---":
            frontmatter_lines: list[str] = []
            idx = 1
            while idx < len(lines):
                if lines[idx].strip() == "---":
                    break
                frontmatter_lines.append(lines[idx])
                idx += 1
            fm, fm_errors = self._parse_simple_yaml("\n".join(frontmatter_lines))
            data.update(fm)
            errors.extend([f"frontmatter:{item}" for item in fm_errors])
        for line in lines:
            stripped = line.strip()
            lower = stripped.lower()
            if not stripped:
                continue
            if stripped.startswith("#") and "name" not in data:
                data["name"] = stripped.lstrip("# ").strip()
            if lower.startswith("name:"):
                data["name"] = stripped.split(":", 1)[1].strip()
            elif lower.startswith("description:"):
                data["description"] = stripped.split(":", 1)[1].strip()
            elif lower.startswith("triggers:"):
                data["triggers"] = self._ensure_list(stripped.split(":", 1)[1].strip())
            elif lower.startswith("when_to_use:"):
                data["when_to_use"] = self._ensure_list(stripped.split(":", 1)[1].strip())
            elif lower.startswith("permissions:"):
                data["permissions"] = self._ensure_list(stripped.split(":", 1)[1].strip())
            elif lower.startswith("tools:") or lower.startswith("required_tools:"):
                data["tools"] = self._ensure_list(stripped.split(":", 1)[1].strip())
            elif lower.startswith("allowed-tools:") or lower.startswith("allowed_tools:"):
                data["allowed_tools"] = self._ensure_list(stripped.split(":", 1)[1].strip())
            elif lower.startswith("trust:") or lower.startswith("trust_level:"):
                data["trust"] = stripped.split(":", 1)[1].strip()
            elif lower.startswith("invocation:"):
                data["invocation"] = stripped.split(":", 1)[1].strip()
            elif lower.startswith("argument-hint:") or lower.startswith("argument_hint:"):
                data["arguments"] = self._ensure_list(stripped.split(":", 1)[1].strip())
        if "description" not in data:
            paragraph = next((line.strip() for line in lines if line.strip() and not line.strip().startswith("#")), "")
            if paragraph:
                data["description"] = paragraph[:240]
        if not data:
            errors.append("skill_markdown_empty")
        return data, errors

    @staticmethod
    def _record_to_entry(record: SkillRecord) -> dict:
        return {
            "skill_id": record.id,
            "skill_name": record.name,
            "source": record.source,
            "status": "disabled" if (record.quarantine or record.status in {"invalid", "disabled", "quarantined"}) else "enabled",
            "required_tools": list(record.tools),
            "tags": list(record.triggers),
            "description": record.description,
            "priority_hint": 0.0,
            "metadata": {
                "trust": {"trust_level": record.trust, "quarantined": record.quarantine, "reason": ",".join(record.errors)},
                "manifest_path": record.manifest_path,
                "skill_md_path": record.skill_md_path,
                "invocation": record.invocation,
                "source_priority": record.source_priority,
            },
            "permissions": list(record.permissions),
        }
