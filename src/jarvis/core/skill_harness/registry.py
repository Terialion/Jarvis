"""Skill registry for runtime and folder-discovered skills."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from time import perf_counter
from typing import Any

from ..result import error_result, ok_result
from .audit import build_skill_audit_record
from .loader import SkillLoader
from .manifest import validate_skill_manifest
from .models import SkillEntry, SkillRecord
from .trust import evaluate_skill_trust


_ALLOWED_STATUS = {"enabled", "disabled"}
_SINGLETON: "SkillRegistry | None" = None


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, SkillEntry] = {}
        self._folder_skills: dict[str, SkillRecord] = {}
        self._shadowed_folder_skills: dict[str, SkillRecord] = {}
        self._audit_log: list[dict] = []
        self._last_discovery: dict[str, Any] = {"roots": [], "warnings": [], "root_priority": {}, "shadowed": []}

    def discover(self, project_root: str | Path | None = None, *, refresh: bool = True) -> dict:
        started = perf_counter()
        if not refresh and self._folder_skills:
            return ok_result(
                {
                    "count": len(self._folder_skills),
                    "roots": list(self._last_discovery.get("roots") or []),
                    "warnings": list(self._last_discovery.get("warnings") or []),
                },
                started,
            )
        loader = SkillLoader()
        discovered = loader.discover_skill_records(project_root or ".")
        self._folder_skills = {}
        self._shadowed_folder_skills = {}
        shadow_meta: list[dict[str, Any]] = []
        for record in discovered["records"]:
            trust_eval = evaluate_skill_trust(
                {
                    "permissions": list(record.permissions),
                    "trust_level": record.trust,
                }
            )
            trust_data = (trust_eval.get("data") if isinstance(trust_eval, dict) else {}) or {}
            quarantined = bool(record.quarantine or trust_data.get("quarantined"))
            status = record.status
            if record.invocation == "disabled":
                status = "disabled"
                quarantined = True
            elif record.status == "invalid":
                status = "invalid"
            elif quarantined:
                status = "quarantined"
            else:
                status = "available"
            updated = replace(
                record,
                quarantine=quarantined,
                status=status,
                metadata={
                    **record.metadata,
                    "trust": trust_data,
                },
            )
            self._folder_skills[updated.id] = updated
            self._audit_log.append(
                build_skill_audit_record(
                    skill_id=updated.id,
                    action="discover",
                    detail={
                        "name": updated.name,
                        "root": updated.root,
                        "status": updated.status,
                        "quarantine": updated.quarantine,
                        "invocation": updated.invocation,
                        "source": updated.source,
                        "source_priority": updated.source_priority,
                    },
                )
            )

        for shadowed in list(discovered.get("shadowed_records") or []):
            key = f"{shadowed.id}@{shadowed.root}"
            self._shadowed_folder_skills[key] = shadowed
            shadow_meta.append(
                {
                    "skill_id": shadowed.id,
                    "root": shadowed.root,
                    "source": shadowed.source,
                    "source_priority": shadowed.source_priority,
                    "shadowed_by": shadowed.shadowed_by,
                }
            )

        self._last_discovery = {
            "roots": discovered["roots"],
            "warnings": discovered["warnings"],
            "root_priority": dict(discovered.get("root_priority") or {}),
            "shadowed": shadow_meta,
        }
        return ok_result(
            {
                "count": len(self._folder_skills),
                "roots": list(discovered["roots"]),
                "warnings": list(discovered["warnings"]),
            },
            started,
        )

    def register_skill(self, skill_entry: dict) -> dict:
        started = perf_counter()
        manifest_validation = validate_skill_manifest(skill_entry)
        if not manifest_validation.get("ok"):
            return error_result(
                "SKILL_MANIFEST_INVALID",
                manifest_validation["error"]["message"],
                {"skill_entry": skill_entry},
                started,
            )
        trust = evaluate_skill_trust(skill_entry)
        if trust.get("ok"):
            trust_data = trust["data"]
            skill_entry = dict(skill_entry)
            skill_entry.setdefault("metadata", {})
            skill_entry["metadata"]["trust"] = trust_data
            source = str(skill_entry.get("source") or "")
            if source in {"third_party", "plugin"} and not skill_entry.get("permissions"):
                trust_data["quarantined"] = True
                trust_data["reason"] = "missing_manifest_permissions"
            if source in {"generated", "learning_loop"}:
                trust_data["quarantined"] = True
                trust_data["reason"] = "generated_skill_requires_approval"
            if trust_data.get("quarantined"):
                skill_entry["status"] = "disabled"
        try:
            entry = self._coerce_entry(skill_entry)
        except ValueError as exc:
            return error_result(
                "SKILL_INVALID_ENTRY",
                "Skill entry is invalid",
                {"reason": str(exc), "skill_entry": skill_entry},
                started,
            )
        self._skills[entry.skill_id] = entry
        self._audit_log.append(build_skill_audit_record(skill_id=entry.skill_id, action="register", detail=entry.to_dict()))
        return ok_result(entry.to_dict(), started)

    def get_skill(self, skill_id: str) -> dict:
        started = perf_counter()
        if skill_id in self._skills:
            return ok_result(self._skills[skill_id].to_dict(), started)
        if skill_id in self._folder_skills:
            return ok_result(self._record_to_legacy_dict(self._folder_skills[skill_id]), started)
        return error_result(
            "SKILL_NOT_FOUND",
            f"Skill not found: {skill_id}",
            {"skill_id": skill_id},
            started,
        )

    def load_skill_body(self, skill_id: str, *, max_bytes: int = 32768) -> dict:
        started = perf_counter()
        record = self._folder_skills.get(skill_id)
        if record is None:
            return error_result("SKILL_NOT_FOUND", f"Skill not found: {skill_id}", {"skill_id": skill_id}, started)
        loader = SkillLoader()
        body, ok = loader.load_skill_body(record, max_bytes=max_bytes)
        updated = replace(record, body_loaded=ok, metadata={**record.metadata, "body_bytes": len(body.encode("utf-8")) if ok else 0})
        self._folder_skills[skill_id] = updated
        self._audit_log.append(
            build_skill_audit_record(
                skill_id=skill_id,
                action="body_load",
                detail={"ok": ok, "bytes": len(body.encode("utf-8")) if ok else 0},
            )
        )
        return ok_result({"skill_id": skill_id, "body_loaded": ok, "body": body if ok else ""}, started)

    def list_skills(self) -> dict:
        started = perf_counter()
        items: list[dict[str, Any]] = [entry.to_dict() for entry in self._skills.values()]
        for record in self._folder_skills.values():
            items.append(self._record_to_legacy_dict(record))
        for record in self._shadowed_folder_skills.values():
            items.append(self._record_to_legacy_dict(record))
        deduped: dict[str, dict[str, Any]] = {}
        for item in items:
            key = str(item.get("skill_id"))
            if key in deduped and str(item.get("status")) != "disabled":
                continue
            deduped[key] = item
        sorted_items = sorted(deduped.values(), key=lambda item: str(item.get("skill_id")))
        return ok_result({"items": sorted_items, "count": len(sorted_items)}, started)

    def list_skill_records(self, *, include_invalid: bool = True, include_shadowed: bool = False) -> list[SkillRecord]:
        records = list(self._folder_skills.values())
        if include_shadowed:
            records += list(self._shadowed_folder_skills.values())
        if include_invalid:
            return records
        return [record for record in records if record.status != "invalid"]

    def find_by_trigger(self, text: str) -> list[SkillRecord]:
        query = (text or "").strip().lower()
        if not query:
            return []
        matched: list[SkillRecord] = []
        for record in self._folder_skills.values():
            if record.quarantine or record.status in {"invalid", "quarantined", "disabled"}:
                continue
            haystack = " ".join(
                [
                    record.id,
                    record.name,
                    record.description,
                    " ".join(record.triggers),
                    " ".join(record.tools),
                    " ".join(record.when_to_use),
                ]
            ).lower()
            if query in haystack or any(trigger.lower() in query for trigger in record.triggers):
                matched.append(record)
        return matched

    def mark_quarantined(self, skill_id: str, reason: str) -> bool:
        if skill_id in self._folder_skills:
            record = self._folder_skills[skill_id]
            self._folder_skills[skill_id] = replace(
                record,
                quarantine=True,
                status="quarantined",
                errors=list(record.errors) + [f"quarantined:{reason}"],
            )
            return True
        if skill_id in self._skills:
            entry = self._skills[skill_id]
            entry.status = "disabled"
            entry.metadata.setdefault("trust", {})
            entry.metadata["trust"]["quarantined"] = True
            entry.metadata["trust"]["reason"] = reason
            return True
        return False

    def is_allowed(self, skill_id: str, policy: dict | None = None) -> bool:
        policy = dict(policy or {})
        deny = {str(item) for item in list(policy.get("denylist") or [])}
        allow = {str(item) for item in list(policy.get("allowlist") or [])}
        require_trusted = bool(policy.get("require_trusted", True))
        network_enabled = bool(policy.get("network_enabled", False))
        if skill_id in deny:
            return False
        if allow and skill_id not in allow:
            return False
        record = self._folder_skills.get(skill_id)
        if record is not None:
            if record.status in {"invalid", "quarantined", "disabled", "shadowed"} or record.quarantine:
                return False
            if record.invocation == "disabled":
                return False
            if require_trusted and record.trust not in {"trusted", "internal", "builtin", "project_trusted"}:
                return False
            if not network_enabled and any("network" in permission.lower() for permission in record.permissions):
                return False
            return True
        entry = self._skills.get(skill_id)
        if entry is None:
            return False
        if entry.status != "enabled":
            return False
        trust_meta = dict(entry.metadata.get("trust") or {})
        if require_trusted and trust_meta.get("trust_level", "untrusted") in {"untrusted", "unknown"}:
            return False
        return True

    def enable_skill(self, skill_id: str) -> dict:
        return self._set_status(skill_id, "enabled")

    def disable_skill(self, skill_id: str) -> dict:
        return self._set_status(skill_id, "disabled")

    def filter_skills(
        self,
        *,
        status: str | None = "enabled",
        tags: list[str] | None = None,
        required_tools: list[str] | None = None,
        source: str | None = None,
    ) -> dict:
        started = perf_counter()
        if status is not None and status not in _ALLOWED_STATUS:
            return error_result(
                "COMMON_INVALID_INPUT",
                "status must be enabled/disabled/None",
                {"status": status},
                started,
            )
        tag_set = {t.strip().lower() for t in (tags or []) if str(t).strip()}
        tool_set = {t.strip() for t in (required_tools or []) if str(t).strip()}
        items = []
        for entry in self._skills.values():
            if status is not None and entry.status != status:
                continue
            if source and entry.source != source:
                continue
            if tag_set and not tag_set.intersection({t.lower() for t in entry.tags}):
                continue
            if tool_set and not tool_set.issubset(set(entry.required_tools)):
                continue
            items.append(entry.to_dict())
        for record in self._folder_skills.values():
            mapped = self._record_to_legacy_dict(record)
            mapped_status = mapped["status"]
            if status is not None and mapped_status != status:
                continue
            if source and mapped.get("source") != source:
                continue
            if tag_set and not tag_set.intersection({t.lower() for t in list(mapped.get("tags") or [])}):
                continue
            if tool_set and not tool_set.issubset(set(mapped.get("required_tools") or [])):
                continue
            items.append(mapped)
        items.sort(key=lambda item: str(item.get("skill_id")))
        return ok_result({"items": items, "count": len(items)}, started)

    def snapshot(self) -> dict:
        started = perf_counter()
        legacy_items = [entry.to_dict() for entry in self._skills.values()]
        folder_items = [self._record_to_legacy_dict(record) for record in self._folder_skills.values()]
        shadowed_items = [self._record_to_legacy_dict(record) for record in self._shadowed_folder_skills.values()]
        items = legacy_items + folder_items + shadowed_items
        enabled = [item["skill_id"] for item in items if item.get("status") == "enabled"]
        disabled = [item["skill_id"] for item in items if item.get("status") == "disabled"]
        return ok_result(
            {
                "count": len(items),
                "enabled_count": len(enabled),
                "disabled_count": len(disabled),
                "enabled_skill_ids": sorted(enabled),
                "disabled_skill_ids": sorted(disabled),
                "items": items,
                "audit_log": list(self._audit_log[-500:]),
                "discovery": dict(self._last_discovery),
            },
            started,
        )

    def _set_status(self, skill_id: str, status: str) -> dict:
        started = perf_counter()
        if skill_id in self._skills:
            self._skills[skill_id].status = status
            return ok_result(self._skills[skill_id].to_dict(), started)
        if skill_id in self._folder_skills:
            record = self._folder_skills[skill_id]
            if status == "enabled":
                updated = replace(record, status="available", quarantine=False, invocation="auto")
            else:
                updated = replace(record, status="quarantined", quarantine=True)
            self._folder_skills[skill_id] = updated
            return ok_result(self._record_to_legacy_dict(updated), started)
        return error_result(
            "SKILL_NOT_FOUND",
            f"Skill not found: {skill_id}",
            {"skill_id": skill_id},
            started,
        )

    @staticmethod
    def _coerce_entry(skill_entry: dict) -> SkillEntry:
        if not isinstance(skill_entry, dict):
            raise ValueError("entry must be a dict")
        skill_id = str(skill_entry.get("skill_id") or "").strip()
        skill_name = str(skill_entry.get("skill_name") or "").strip()
        source = str(skill_entry.get("source") or "").strip()
        if not skill_id or not skill_name or not source:
            raise ValueError("skill_id/skill_name/source are required")
        required_tools = [str(t).strip() for t in list(skill_entry.get("required_tools") or []) if str(t).strip()]
        tags = [str(t).strip() for t in list(skill_entry.get("tags") or []) if str(t).strip()]
        status = str(skill_entry.get("status") or "enabled").strip().lower()
        if status not in _ALLOWED_STATUS:
            status = "enabled"
        return SkillEntry(
            skill_id=skill_id,
            skill_name=skill_name,
            source=source,
            status=status,
            required_tools=required_tools,
            tags=tags,
            description=str(skill_entry.get("description") or "").strip(),
            priority_hint=float(skill_entry.get("priority_hint") or 0.0),
            metadata=dict(skill_entry.get("metadata") or {}),
        )

    @staticmethod
    def _record_to_legacy_dict(record: SkillRecord) -> dict[str, Any]:
        trust_meta = dict(record.metadata.get("trust") or {})
        return {
            "id": record.id,
            "name": record.name,
            "skill_id": record.id,
            "skill_name": record.name,
            "source": record.source,
            "source_priority": int(record.source_priority),
            "invocation": record.invocation,
            "status": "disabled"
            if (record.quarantine or record.status in {"invalid", "quarantined", "disabled", "shadowed"})
            else "enabled",
            "required_tools": list(record.tools),
            "tags": list(record.triggers),
            "triggers": list(record.triggers),
            "when_to_use": list(record.when_to_use),
            "description": record.description,
            "permissions": list(record.permissions),
            "allowed_tools": list(record.allowed_tools),
            "arguments": list(record.arguments),
            "dynamic_context": bool(record.dynamic_context),
            "subagent": bool(record.subagent),
            "trust": record.trust,
            "quarantine": bool(record.quarantine),
            "root": record.root,
            "manifest_path": record.manifest_path,
            "skill_md_path": record.skill_md_path,
            "shadowed_by": record.shadowed_by,
            "body_loaded": bool(record.body_loaded),
            "errors": list(record.errors),
            "metadata": {
                **dict(record.metadata),
                "trust": {
                    "trust_level": trust_meta.get("trust_level", record.trust),
                    "quarantined": bool(record.quarantine or trust_meta.get("quarantined")),
                    "reason": trust_meta.get("reason", ""),
                },
            },
        }


def get_skill_registry(project_root: str | Path | None = None, *, refresh: bool = False) -> SkillRegistry:
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = SkillRegistry()
    _SINGLETON.discover(project_root or ".", refresh=refresh)
    return _SINGLETON
