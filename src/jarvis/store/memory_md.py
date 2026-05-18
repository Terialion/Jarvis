"""Markdown-based memory store — human-editable .md files with frontmatter.

Follows Claude Code's memory format: MEMORY.md index + memory/*.md files.
Each file uses YAML-like frontmatter (name, description, type) + markdown body.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class MemoryEntry:
    name: str
    description: str
    memory_type: str  # user, feedback, project, reference
    content: str
    file_path: Path | None = None


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Extract frontmatter (--- ... ---) and body from markdown text."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, text

    end_idx = 1
    meta: dict[str, str] = {}
    while end_idx < len(lines):
        line = lines[end_idx].strip()
        if line == "---":
            end_idx += 1
            break
        if ":" in line:
            key, _, val = line.partition(":")
            meta[key.strip()] = val.strip()
        end_idx += 1

    body = "\n".join(lines[end_idx:]).strip()
    return meta, body


def _format_frontmatter(meta: dict[str, str], body: str) -> str:
    """Format entry as markdown with frontmatter."""
    lines = ["---"]
    for key in ("name", "description", "type"):
        if key in meta:
            lines.append(f"{key}: {meta[key]}")
    lines.append("---")
    lines.append("")
    lines.append(body)
    return "\n".join(lines) + "\n"


class MarkdownMemoryStore:
    """Reads/writes memory as markdown files — human-editable, git-trackable."""

    def __init__(self, base_dir: Path | str) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.base_dir / "MEMORY.md"
        self._write_lock = threading.Lock()

    # ── Read ──────────────────────────────────────────────────────

    def load_all(self) -> list[MemoryEntry]:
        """Load all memory entries from markdown files."""
        entries: list[MemoryEntry] = []
        if not self.base_dir.exists():
            return entries

        for md_file in sorted(self.base_dir.glob("*.md")):
            if md_file.name == "MEMORY.md":
                continue
            try:
                text = md_file.read_text(encoding="utf-8", errors="replace")
                meta, body = _parse_frontmatter(text)
                if meta.get("name") and body:
                    entries.append(MemoryEntry(
                        name=meta["name"],
                        description=meta.get("description", ""),
                        memory_type=meta.get("type", "project"),
                        content=body,
                        file_path=md_file,
                    ))
            except Exception:
                continue
        return entries

    def load_by_type(self, memory_type: str) -> list[MemoryEntry]:
        return [e for e in self.load_all() if e.memory_type == memory_type]

    def load_by_name(self, name: str) -> MemoryEntry | None:
        """Load a single memory entry by name."""
        safe_name = name.replace("/", "_").replace("\\", "_").replace(" ", "_").replace(":", "_")
        file_path = self.base_dir / f"{safe_name}.md"
        if not file_path.exists():
            return None
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
            meta, body = _parse_frontmatter(text)
            if meta.get("name") and body:
                return MemoryEntry(
                    name=meta["name"],
                    description=meta.get("description", ""),
                    memory_type=meta.get("type", "project"),
                    content=body,
                    file_path=file_path,
                )
        except Exception:
            pass
        return None

    def load_index(self) -> list[str]:
        """Return list of entries referenced in MEMORY.md index."""
        if not self.index_path.exists():
            return []
        lines = self.index_path.read_text(encoding="utf-8", errors="replace").split("\n")
        refs: list[str] = []
        for line in lines:
            line = line.strip()
            if line.startswith("- [") and "](" in line and line.endswith(".md)"):
                # Extract filename from markdown link: "- [Title](file.md) — desc"
                start = line.index("](") + 2
                end = line.index(".md)", start) + 3
                refs.append(line[start:end])
        return refs

    # ── Write ─────────────────────────────────────────────────────

    def write(self, entry: MemoryEntry) -> Path:
        """Write a memory entry to a markdown file and update MEMORY.md."""
        safe_name = entry.name.replace("/", "_").replace("\\", "_").replace(" ", "_").replace(":", "_")
        file_name = f"{safe_name}.md"
        file_path = self.base_dir / file_name

        meta = {
            "name": entry.name,
            "description": entry.description,
            "type": entry.memory_type,
        }

        with self._write_lock:
            file_path.write_text(
                _format_frontmatter(meta, entry.content),
                encoding="utf-8",
            )
            self._update_index(entry, file_name)

        return file_path

    def _update_index(self, entry: MemoryEntry, file_name: str) -> None:
        """Add or update entry in MEMORY.md index."""
        existing = ""
        if self.index_path.exists():
            existing = self.index_path.read_text(encoding="utf-8", errors="replace")

        hook = entry.description[:100] if entry.description else "(no description)"
        new_line = f"- [{entry.name}]({file_name}) — {hook}"

        # Replace existing line for same file or append
        marker = f"]({file_name})"
        lines = existing.split("\n")
        replaced = False
        for i, line in enumerate(lines):
            if marker in line:
                lines[i] = new_line
                replaced = True
                break

        if not replaced:
            # Remove trailing blank lines, append, add trailing newline
            while lines and not lines[-1].strip():
                lines.pop()
            lines.append(new_line)
            lines.append("")  # trailing newline

        self.index_path.write_text("\n".join(lines), encoding="utf-8")

    def delete(self, name: str) -> bool:
        """Delete a memory entry file and remove from MEMORY.md."""
        safe_name = name.replace("/", "_").replace("\\", "_").replace(" ", "_").replace(":", "_")
        file_name = f"{safe_name}.md"
        file_path = self.base_dir / file_name

        with self._write_lock:
            deleted = False
            if file_path.exists():
                file_path.unlink()
                deleted = True

            # Remove from index
            if self.index_path.exists():
                marker = f"]({file_name})"
                lines = self.index_path.read_text(encoding="utf-8", errors="replace").split("\n")
                lines = [l for l in lines if marker not in l]
                self.index_path.write_text("\n".join(lines), encoding="utf-8")

            return deleted

    def rebuild_index(self) -> None:
        """Rebuild MEMORY.md from all .md files in the directory."""
        entries = self.load_all()
        lines: list[str] = []
        for e in entries:
            file_name = e.file_path.name if e.file_path else f"{e.name}.md"
            hook = e.description[:100] if e.description else e.content[:100]
            lines.append(f"- [{e.name}]({file_name}) — {hook}")
        with self._write_lock:
            self.index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # ── Search ────────────────────────────────────────────────────

    def search(self, query: str) -> list[MemoryEntry]:
        """Simple text-based search across all memory entries."""
        if not query:
            return []
        terms = query.lower().split()
        results: list[MemoryEntry] = []
        for entry in self.load_all():
            text = f"{entry.name} {entry.description} {entry.content}".lower()
            if all(term in text for term in terms):
                results.append(entry)
        return results

    # ── Sync helpers ──────────────────────────────────────────────

    def to_dicts(self) -> list[dict[str, Any]]:
        """Export all entries as dicts suitable for SQLite sync."""
        return [
            {
                "memory_type": e.memory_type,
                "key": e.name,
                "value": e.content,
                "metadata": {"description": e.description, "source": "markdown"},
            }
            for e in self.load_all()
        ]
