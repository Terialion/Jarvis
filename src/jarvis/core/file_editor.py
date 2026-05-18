"""File Editor module for Jarvis Core Phase 1."""

from __future__ import annotations

import difflib
from pathlib import Path
from time import perf_counter
from typing import Callable

from .result import error_result, ok_result
from .safety_guard import SafetyGuard


WriteGuard = Callable[[Path], bool]


class FileEditor:
    """Edit files with consistent results and safety hook points."""

    def __init__(
        self,
        project_root: str | None = None,
        write_guard: WriteGuard | None = None,
        safety_guard: SafetyGuard | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve() if project_root else None
        self.write_guard = write_guard
        self.safety_guard = safety_guard
        self._snapshots: dict[str, str] = {}

    def replace_text(self, path: str, old: str, new: str) -> dict:
        started = perf_counter()
        validation = self._validate_write_target(path, create=False, started=started)
        if validation:
            return validation

        target = Path(path)
        try:
            before = target.read_text(encoding="utf-8")
            if old not in before:
                return error_result(
                    "EDIT_TARGET_NOT_FOUND",
                    "Target text not found",
                    {"path": path, "old": old},
                    started,
                )
            count = before.count(old)
            if count > 1:
                return error_result(
                    "EDIT_AMBIGUOUS_MATCH",
                    f"old_string matches {count} occurrences in the file; must be unique",
                    {"path": path, "occurrences": count, "old": old[:200]},
                    started,
                )
            after = before.replace(old, new, 1)
            self._snapshots[str(target.resolve())] = before
            target.write_text(after, encoding="utf-8")
            return ok_result({"path": str(target), "replaced": True}, started)
        except Exception as exc:
            return error_result(
                "EDIT_APPLY_FAILED",
                "Failed to apply replace_text",
                {"path": path, "exception": str(exc)},
                started,
            )

    def insert_text(self, path: str, anchor: str, content: str, position: str = "after") -> dict:
        started = perf_counter()
        validation = self._validate_write_target(path, create=False, started=started)
        if validation:
            return validation
        if position not in {"before", "after"}:
            return error_result(
                "COMMON_INVALID_INPUT",
                "position must be 'before' or 'after'",
                {"position": position},
                started,
            )

        target = Path(path)
        try:
            before = target.read_text(encoding="utf-8")
            if anchor not in before:
                return error_result(
                    "EDIT_TARGET_NOT_FOUND",
                    "Anchor text not found",
                    {"path": path, "anchor": anchor},
                    started,
                )
            insert_block = f"{content}\n{anchor}" if position == "before" else f"{anchor}\n{content}"
            after = before.replace(anchor, insert_block, 1)
            self._snapshots[str(target.resolve())] = before
            target.write_text(after, encoding="utf-8")
            return ok_result({"path": str(target), "inserted": True, "position": position}, started)
        except Exception as exc:
            return error_result(
                "EDIT_APPLY_FAILED",
                "Failed to apply insert_text",
                {"path": path, "exception": str(exc)},
                started,
            )

    def write_file(self, path: str, content: str, create: bool = True) -> dict:
        started = perf_counter()
        validation = self._validate_write_target(path, create=create, started=started)
        if validation:
            return validation

        target = Path(path)
        try:
            existed_before = target.exists()
            if target.exists():
                self._snapshots[str(target.resolve())] = target.read_text(encoding="utf-8")
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return ok_result({"path": str(target), "created": (not existed_before) and create}, started)
        except PermissionError:
            return error_result(
                "EDIT_WRITE_DENIED",
                "Write denied by filesystem permissions",
                {"path": path},
                started,
            )
        except Exception as exc:
            return error_result(
                "EDIT_APPLY_FAILED",
                "Failed to write file",
                {"path": path, "exception": str(exc)},
                started,
            )

    def diff(self, path: str) -> dict:
        started = perf_counter()
        target = Path(path)
        if not target.exists():
            return error_result(
                "EDIT_TARGET_NOT_FOUND",
                f"Target file not found: {path}",
                {"path": path},
                started,
            )

        key = str(target.resolve())
        before = self._snapshots.get(key)
        if before is None:
            return error_result(
                "EDIT_DIFF_FAILED",
                "No baseline snapshot found for diff",
                {"path": path},
                started,
            )

        try:
            after = target.read_text(encoding="utf-8")
            diff_lines = list(
                difflib.unified_diff(
                    before.splitlines(),
                    after.splitlines(),
                    fromfile=f"{target.name}:before",
                    tofile=f"{target.name}:after",
                    lineterm="",
                )
            )
            changed_lines = len([ln for ln in diff_lines if ln.startswith("+") or ln.startswith("-")]) - 2
            return ok_result(
                {
                    "path": str(target),
                    "diff_text": "\n".join(diff_lines),
                    "changed_lines": max(changed_lines, 0),
                    "summary": "diff generated",
                },
                started,
            )
        except Exception as exc:
            return error_result(
                "EDIT_DIFF_FAILED",
                "Failed to generate diff",
                {"path": path, "exception": str(exc)},
                started,
            )

    def _validate_write_target(self, path: str, create: bool, started: float) -> dict | None:
        target = Path(path).resolve()
        if self.project_root and not self._is_within_root(target, self.project_root):
            return error_result(
                "EDIT_WRITE_DENIED",
                "Write path is outside project root",
                {"path": str(target), "project_root": str(self.project_root)},
                started,
            )
        if self.write_guard and not self.write_guard(target):
            return error_result(
                "EDIT_WRITE_DENIED",
                "Write blocked by policy hook",
                {"path": str(target)},
                started,
            )
        if self.safety_guard and self.project_root:
            guard_result = self.safety_guard.validate_write(str(target), str(self.project_root))
            if not guard_result.get("ok"):
                return error_result(
                    "EDIT_WRITE_DENIED",
                    "Write validation failed in safety guard",
                    {"path": str(target), "guard_error": guard_result.get("error")},
                    started,
                )
            guard_data = guard_result.get("data") or {}
            if not guard_data.get("allowed", False):
                return error_result(
                    "EDIT_WRITE_DENIED",
                    "Write blocked by safety guard",
                    {
                        "path": str(target),
                        "reason_code": guard_data.get("reason_code"),
                        "needs_confirmation": bool(guard_data.get("needs_confirmation")),
                    },
                    started,
                )
            if guard_data.get("needs_confirmation"):
                return error_result(
                    "EDIT_WRITE_DENIED",
                    "Write requires user confirmation before execution",
                    {
                        "path": str(target),
                        "reason_code": guard_data.get("reason_code"),
                        "needs_confirmation": True,
                    },
                    started,
                )
        if not target.exists() and not create:
            return error_result(
                "EDIT_TARGET_NOT_FOUND",
                f"Target file not found: {path}",
                {"path": path},
                started,
            )
        return None

    @staticmethod
    def _is_within_root(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False
