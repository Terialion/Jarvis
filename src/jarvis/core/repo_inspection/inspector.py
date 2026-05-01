"""Main orchestration for read-only repository inspection."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from .readers import read_text_file_limited, select_key_files
from .safety import is_sensitive_path
from .schema import RepoInspectionRequest, RepoInspectionResult, SkippedFileRecord
from .summarizer import (
    build_architecture_summary,
    build_next_suggestions,
    detect_entrypoints,
    detect_important_modules,
    detect_project_type,
    detect_test_layout,
)
from .trace import append_repo_inspection_trace
from .workspace import ensure_within_workspace, list_tree_limited, resolve_workspace_root

REPO_TRACE_PATH = Path("temp/repo_inspection/inspections.jsonl")


def inspect_repo(request: RepoInspectionRequest, *, session_id: str = "cli_shell") -> RepoInspectionResult:
    workspace_root = resolve_workspace_root(request.workspace_root)
    entries, skipped_dirs = list_tree_limited(workspace_root, max_entries=request.max_tree_entries)
    project_type = detect_project_type(workspace_root)
    key_files = select_key_files(workspace_root, entries)

    files_read = []
    files_skipped = [SkippedFileRecord(path=p.as_posix(), reason=r) for p, r in skipped_dirs]
    total_bytes = 0
    considered: list[str] = []

    for p in key_files:
        considered.append(p.relative_to(workspace_root).as_posix())
        try:
            ensure_within_workspace(p, workspace_root)
        except ValueError:
            files_skipped.append(SkippedFileRecord(path=p.as_posix(), reason="outside_workspace"))
            continue
        if len(files_read) >= request.max_files_read:
            files_skipped.append(SkippedFileRecord(path=p.as_posix(), reason="limit"))
            continue
        text, rec, skip = read_text_file_limited(
            p,
            max_file_bytes=request.max_file_bytes,
            remaining_budget=max(0, request.max_total_read_bytes - total_bytes),
        )
        if skip is not None:
            files_skipped.append(skip)
            continue
        if rec is None:
            files_skipped.append(SkippedFileRecord(path=p.as_posix(), reason="read_error"))
            continue
        total_bytes += rec.bytes_read
        files_read.append(rec)

    config_files = [x for x in considered if Path(x).name in {"pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "package.json"}]
    instruction_files = [x for x in considered if Path(x).name in {"AGENTS.md", "JARVIS.md"}]
    entrypoints = detect_entrypoints(entries, workspace_root)
    important_modules = detect_important_modules(entries, workspace_root)
    test_layout = detect_test_layout(entries, workspace_root)

    safety_notes = [
        "Inspection was read-only.",
        "No shell commands were executed.",
        "No files were modified.",
        "Sensitive files were skipped.",
    ]
    if any(is_sensitive_path(Path(s.path)) for s in files_skipped):
        safety_notes.append("Sensitive path denylist was enforced.")

    result = RepoInspectionResult(
        workspace_root=workspace_root.as_posix(),
        project_type=project_type,
        tree_entries_sample=[p.relative_to(workspace_root).as_posix() for p in entries[:30]],
        files_considered=considered,
        files_read=files_read,
        files_skipped=files_skipped,
        total_bytes_read=total_bytes,
        entrypoints=entrypoints,
        important_modules=important_modules,
        test_layout=test_layout,
        config_files=config_files,
        instruction_files=instruction_files,
        architecture_summary=build_architecture_summary(project_type),
        safety_notes=safety_notes,
        risks=[],
        next_suggestions=build_next_suggestions(),
    )

    trace_payload: dict[str, Any] = {
        "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "session_id": session_id,
        "workspace_root": result.workspace_root,
        "user_input": request.user_input,
        "files_read": [r.path for r in result.files_read],
        "files_skipped": [{"path": s.path, "reason": s.reason} for s in result.files_skipped],
        "project_type": result.project_type,
        "total_bytes_read": result.total_bytes_read,
        "safety_notes": result.safety_notes,
    }
    append_repo_inspection_trace(REPO_TRACE_PATH, trace_payload)
    return result
