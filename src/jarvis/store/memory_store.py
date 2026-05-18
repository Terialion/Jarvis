"""Durable typed memory store backed by pure Markdown files.

Follows Claude Code's format: .jarvis/memory/MEMORY.md index + memory/*.md files.
Each file uses YAML-like frontmatter (name, description, type) + markdown body.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from .memory_md import MarkdownMemoryStore, MemoryEntry
from .redaction import redact_text_for_persistence


class MemoryStore:
    """Typed memory backed by pure Markdown — human-editable, git-trackable."""

    def __init__(self, memory_md_dir: str | Path | None = None) -> None:
        md_dir = Path(memory_md_dir) if memory_md_dir else Path(".jarvis/memory")
        self._md = MarkdownMemoryStore(md_dir)

    @property
    def memory_md(self) -> MarkdownMemoryStore:
        return self._md

    # ── Typed memory (markdown-backed) ──────────────────────────────

    def search(
        self,
        query: str,
        *,
        memory_type: str | None = None,
        project_id: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        results = self._md.search(query or "")
        if memory_type:
            results = [e for e in results if e.memory_type == memory_type]
        return [self._entry_to_dict(e) for e in results[:max(1, int(limit))]]

    def get_typed(
        self,
        *,
        memory_type: str | None = None,
        project_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        if memory_type:
            entries = self._md.load_by_type(memory_type)
        else:
            entries = self._md.load_all()
        return [self._entry_to_dict(e) for e in entries[:max(1, int(limit))]]

    def remember(
        self,
        memory_type: str,
        key: str,
        value: str,
        *,
        project_id: str | None = None,
        source_turn_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        desc = str(metadata.get("description", "")) if metadata else ""
        entry = MemoryEntry(
            name=str(key).strip(),
            description=desc,
            memory_type=memory_type,
            content=str(value),
        )
        self._md.write(entry)
        return self._entry_to_dict(entry)

    def write_feedback(
        self,
        key: str,
        value: str,
        *,
        project_id: str | None = None,
        source_turn_id: str | None = None,
    ) -> dict[str, Any]:
        return self.remember("feedback", key, value, project_id=project_id)

    def write_reference(
        self,
        key: str,
        value: str,
        *,
        project_id: str | None = None,
        source_turn_id: str | None = None,
    ) -> dict[str, Any]:
        return self.remember("reference", key, value, project_id=project_id)

    def write_user_profile(self, key: str, value: str) -> dict[str, Any]:
        return self.remember("user_profile", key, value)

    def delete_typed(self, memory_id: str) -> None:
        # memory_id is typically the entry name in this system
        self._md.delete(memory_id)

    # ── User memory (backward-compat KV mapped to markdown) ────────

    def get_user_memory(self) -> dict[str, str]:
        entries = self._md.load_by_type("user")
        return {e.name: e.content for e in entries}

    def set_user_memory(self, key: str, value: str) -> dict[str, Any]:
        entry = MemoryEntry(
            name=str(key),
            description="",
            memory_type="user",
            content=str(value),
        )
        self._md.write(entry)
        return self._entry_to_dict(entry)

    def delete_user_memory(self, key: str) -> None:
        self._md.delete(key)

    def clear_user_memory(self) -> None:
        for entry in self._md.load_by_type("user"):
            self._md.delete(entry.name)

    # ── Project memory (backward-compat KV mapped to markdown) ─────

    def get_project_memory(self, project_id: str) -> dict[str, str]:
        entries = self._md.load_by_type("project")
        prefix = f"{project_id}/"
        return {
            e.name[len(prefix):] if e.name.startswith(prefix) else e.name: e.content
            for e in entries
            if e.name.startswith(prefix) or not prefix
        }

    def set_project_memory(self, project_id: str, key: str, value: str) -> dict[str, Any]:
        entry = MemoryEntry(
            name=f"{project_id}/{str(key)}",
            description="",
            memory_type="project",
            content=str(value),
        )
        self._md.write(entry)
        return self._entry_to_dict(entry)

    def delete_project_memory(self, project_id: str, key: str) -> None:
        self._md.delete(f"{project_id}/{str(key)}")

    def clear_project_memory(self, project_id: str) -> None:
        for entry in self._md.load_by_type("project"):
            if entry.name.startswith(f"{project_id}/"):
                self._md.delete(entry.name)

    # ── Convenience ─────────────────────────────────────────────────

    def write_to_both(self, memory_type: str, key: str, value: str, *, description: str = "") -> tuple[dict[str, Any], Path]:
        """Write to markdown (sole source of truth)."""
        entry = MemoryEntry(
            name=key,
            description=description,
            memory_type=memory_type,
            content=value,
        )
        md_path = self._md.write(entry)
        return self._entry_to_dict(entry), md_path

    # ── Helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _entry_to_dict(entry: MemoryEntry) -> dict[str, Any]:
        return {
            "memory_id": entry.name,
            "memory_type": entry.memory_type,
            "key": entry.name,
            "value_raw": entry.content,
            "value_redacted": redact_text_for_persistence(entry.content),
            "value": entry.content,  # convenience alias
            "project_id": None,
            "is_global": True,
            "source_turn_id": None,
            "metadata": {"description": entry.description, "source": "markdown"},
            "updated_at": "",
        }
