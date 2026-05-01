from __future__ import annotations

from typing import Any

from ..skill_harness.registry import get_skill_registry
from .metadata import SkillCommandMetadata


def list_user_invocable_skill_commands(
    *,
    registry_items: list[dict[str, Any]] | None = None,
) -> list[SkillCommandMetadata]:
    items = registry_items
    if items is None:
        items = (get_skill_registry(refresh=False).list_skills().get("data") or {}).get("items", [])
    rows: list[SkillCommandMetadata] = []
    for item in items:
        metadata = dict(item.get("metadata") or {})
        row = SkillCommandMetadata(
            name=str(item.get("skill_id") or item.get("id") or item.get("skill_name") or ""),
            command_name=str(metadata.get("command_name") or item.get("skill_id") or item.get("id") or "").strip().lower(),
            description=str(item.get("description") or ""),
            user_invocable=bool(metadata.get("user_invocable", True)),
            command_dispatch=metadata.get("command_dispatch"),
            command_tool=metadata.get("command_tool"),
            risk_level=str(metadata.get("risk_level") or "medium"),
        )
        if row.command_name and row.user_invocable:
            rows.append(row)
    return rows


def resolve_user_invocable_skill_command(
    command_name: str,
    *,
    registry_items: list[dict[str, Any]] | None = None,
) -> SkillCommandMetadata | None:
    needle = str(command_name or "").strip().lower()
    if not needle:
        return None
    for item in list_user_invocable_skill_commands(registry_items=registry_items):
        aliases = {item.command_name, item.name.strip().lower()}
        if needle in aliases:
            return item
    return None

