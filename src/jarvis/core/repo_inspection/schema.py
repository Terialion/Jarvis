"""Schema types for read-only repository inspection."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class RepoInspectionRequest:
    workspace_root: Path
    user_input: str = ""
    max_file_bytes: int = 65536
    max_total_read_bytes: int = 524288
    max_files_read: int = 30
    max_tree_entries: int = 300


@dataclass
class ReadFileRecord:
    path: str
    bytes_read: int


@dataclass
class SkippedFileRecord:
    path: str
    reason: str


@dataclass
class RepoInspectionResult:
    workspace_root: str
    project_type: list[str] = field(default_factory=list)
    tree_entries_sample: list[str] = field(default_factory=list)
    files_considered: list[str] = field(default_factory=list)
    files_read: list[ReadFileRecord] = field(default_factory=list)
    files_skipped: list[SkippedFileRecord] = field(default_factory=list)
    total_bytes_read: int = 0
    entrypoints: list[str] = field(default_factory=list)
    important_modules: list[str] = field(default_factory=list)
    test_layout: list[str] = field(default_factory=list)
    config_files: list[str] = field(default_factory=list)
    instruction_files: list[str] = field(default_factory=list)
    architecture_summary: str = ""
    safety_notes: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    next_suggestions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
