"""Repo Reader module for Jarvis Core Phase 1."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Iterable

from .result import error_result, ok_result


class RepoReader:
    """Read and search repository content with uniform result shape."""

    def list_tree(self, repo_path: str, max_depth: int = 3) -> dict:
        started = perf_counter()
        root = Path(repo_path)
        if not root.exists() or not root.is_dir():
            return error_result(
                "REPO_INVALID_ROOT",
                f"Repository root is invalid: {repo_path}",
                {"repo_path": repo_path},
                started,
            )
        if max_depth < 0:
            return error_result(
                "COMMON_INVALID_INPUT",
                "max_depth must be >= 0",
                {"max_depth": max_depth},
                started,
            )

        try:
            items: list[dict] = []
            for path in sorted(root.rglob("*")):
                relative = path.relative_to(root)
                depth = len(relative.parts)
                if depth > max_depth:
                    continue
                items.append(
                    {
                        "path": str(relative).replace("\\", "/"),
                        "type": "dir" if path.is_dir() else "file",
                        "depth": depth,
                    }
                )
            return ok_result(
                {"repo_path": str(root), "max_depth": max_depth, "items": items},
                started,
            )
        except Exception as exc:  # pragma: no cover - defensive
            return error_result(
                "COMMON_INTERNAL_ERROR",
                "Failed to list repository tree",
                {"exception": str(exc)},
                started,
            )

    def read_file(
        self,
        path: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> dict:
        started = perf_counter()
        file_path = Path(path)
        if not file_path.exists() or not file_path.is_file():
            return error_result(
                "REPO_FILE_NOT_FOUND",
                f"File not found: {path}",
                {"path": path},
                started,
            )

        if start_line is not None and start_line < 1:
            return error_result(
                "COMMON_INVALID_INPUT",
                "start_line must be >= 1",
                {"start_line": start_line},
                started,
            )
        if end_line is not None and end_line < 1:
            return error_result(
                "COMMON_INVALID_INPUT",
                "end_line must be >= 1",
                {"end_line": end_line},
                started,
            )
        if start_line is not None and end_line is not None and end_line < start_line:
            return error_result(
                "COMMON_INVALID_INPUT",
                "end_line must be >= start_line",
                {"start_line": start_line, "end_line": end_line},
                started,
            )

        try:
            lines = file_path.read_text(encoding="utf-8").splitlines()
            selected_start = start_line or 1
            selected_end = end_line or len(lines)
            selected = lines[selected_start - 1 : selected_end]
            return ok_result(
                {
                    "path": str(file_path),
                    "start_line": selected_start,
                    "end_line": selected_end,
                    "content": "\n".join(selected),
                },
                started,
            )
        except UnicodeDecodeError:
            return error_result(
                "COMMON_INVALID_INPUT",
                "Only UTF-8 text files are supported",
                {"path": path},
                started,
            )
        except Exception as exc:  # pragma: no cover - defensive
            return error_result(
                "COMMON_INTERNAL_ERROR",
                "Failed to read file",
                {"path": path, "exception": str(exc)},
                started,
            )

    def search_files(self, repo_path: str, pattern: str, max_results: int = 20) -> dict:
        started = perf_counter()
        root = Path(repo_path)
        if not root.exists() or not root.is_dir():
            return error_result(
                "REPO_INVALID_ROOT",
                f"Repository root is invalid: {repo_path}",
                {"repo_path": repo_path},
                started,
            )
        if not pattern:
            return error_result(
                "COMMON_INVALID_INPUT",
                "pattern must be non-empty",
                {"pattern": pattern},
                started,
            )

        try:
            matches = self._search_text(root=root, needle=pattern, max_results=max_results)
            return ok_result(
                {"repo_path": str(root), "pattern": pattern, "matches": matches},
                started,
            )
        except Exception as exc:
            return error_result(
                "REPO_SEARCH_FAILED",
                "File search failed",
                {"pattern": pattern, "exception": str(exc)},
                started,
            )

    def search_symbol(self, repo_path: str, symbol: str, max_results: int = 20) -> dict:
        started = perf_counter()
        root = Path(repo_path)
        if not root.exists() or not root.is_dir():
            return error_result(
                "REPO_INVALID_ROOT",
                f"Repository root is invalid: {repo_path}",
                {"repo_path": repo_path},
                started,
            )
        if not symbol:
            return error_result(
                "COMMON_INVALID_INPUT",
                "symbol must be non-empty",
                {"symbol": symbol},
                started,
            )

        try:
            matches = self._search_text(root=root, needle=symbol, max_results=max_results)
            if not matches:
                return error_result(
                    "REPO_SYMBOL_NOT_FOUND",
                    f"Symbol not found: {symbol}",
                    {"symbol": symbol},
                    started,
                )
            return ok_result(
                {"repo_path": str(root), "symbol": symbol, "matches": matches},
                started,
            )
        except Exception as exc:
            return error_result(
                "REPO_SEARCH_FAILED",
                "Symbol search failed",
                {"symbol": symbol, "exception": str(exc)},
                started,
            )

    def _search_text(self, root: Path, needle: str, max_results: int) -> list[dict]:
        results: list[dict] = []
        for file_path in self._iter_text_files(root):
            try:
                content = file_path.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                continue
            rel = str(file_path.relative_to(root)).replace("\\", "/")
            for line_no, line in enumerate(content, start=1):
                if needle in line:
                    results.append({"path": rel, "line": line_no, "snippet": line.strip()})
                    if len(results) >= max_results:
                        return results
        return results

    def _iter_text_files(self, root: Path) -> Iterable[Path]:
        skip_dirs = {".git", "__pycache__", ".venv", "node_modules"}
        for path in root.rglob("*"):
            if path.is_dir() and path.name in skip_dirs:
                continue
            if path.is_file():
                yield path

