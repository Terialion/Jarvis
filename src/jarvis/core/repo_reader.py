"""Repo Reader module for Jarvis Core Phase 1."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Iterable

from .result import error_result, ok_result


class RepoReader:
    """Read and search repository content with uniform result shape."""

    # Directories excluded from tree listing (match Claude Code behavior)
    _SKIP_TREE_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache",
                       "node_modules", ".jarvis", ".tox", ".eggs", ".mypy_cache",
                       ".ruff_cache", "logs", ".workbuddy"}

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
            max_items = 500  # prevent context bloat
            # Breadth-first ordering: shallow items first so top-level dirs
            # (like workspace/) aren't buried under deep subtrees (like codex/).
            for path in sorted(root.rglob("*"),
                               key=lambda p: (len(p.relative_to(root).parts),
                                              str(p.relative_to(root)).lower())):
                relative = path.relative_to(root)
                depth = len(relative.parts)
                if depth > max_depth:
                    continue
                # Skip noise directories at the top level
                if depth >= 1 and relative.parts[0] in self._SKIP_TREE_DIRS:
                    continue
                items.append(
                    {
                        "path": str(relative).replace("\\", "/"),
                        "type": "dir" if path.is_dir() else "file",
                        "depth": depth,
                    }
                )
                if len(items) >= max_items:
                    items.append({"path": "...", "type": "truncated", "depth": 1,
                                  "note": f"output truncated at {max_items} items"})
                    break
            # Format as readable tree string (matching Claude Code output style)
            tree_text = self._format_tree(items)
            return ok_result(
                {"repo_path": str(root), "max_depth": max_depth, "tree": tree_text,
                 "item_count": len([i for i in items if i.get("type") != "truncated"])},
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

    _RG_PATH: str | None = None  # cached ripgrep path

    @classmethod
    def _find_rg(cls) -> str | None:
        if cls._RG_PATH is not None:
            return cls._RG_PATH or None
        import shutil
        # Check first in project bin/
        project_bin = Path(__file__).resolve().parent.parent.parent.parent / "bin" / "rg.exe"
        if project_bin.exists():
            cls._RG_PATH = str(project_bin)
            return cls._RG_PATH
        found = shutil.which("rg")
        cls._RG_PATH = found or ""
        return found

    def grep(self, repo_path: str, pattern: str, *,
             glob: str | None = None,
             max_results: int = 20,
             context: int = 0,
             multiline: bool = False,
             ) -> dict:
        """Fast content search using ripgrep (fallback: Python scan).

        Mirrors Claude Code's Grep tool: pattern, glob filter, context lines,
        multiline mode, max_results cap.
        """
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
            matches = self._grep_rg(root, pattern, glob=glob, max_results=max_results,
                                    context=context, multiline=multiline)
            return ok_result(
                {"repo_path": str(root), "pattern": pattern, "matches": matches},
                started,
            )
        except Exception as exc:
            return error_result(
                "REPO_SEARCH_FAILED",
                "Grep search failed",
                {"pattern": pattern, "exception": str(exc)},
                started,
            )

    def _grep_rg(self, root: Path, pattern: str, *, glob: str | None,
                 max_results: int, context: int, multiline: bool) -> list[dict]:
        """Run ripgrep subprocess; fall back to Python scan on failure."""
        rg = self._find_rg()
        if rg:
            try:
                return self._run_rg(rg, root, pattern, glob=glob,
                                    max_results=max_results, context=context,
                                    multiline=multiline)
            except Exception:
                pass  # fall through to Python scan
        return self._search_text(root, pattern, max_results)

    @staticmethod
    def _run_rg(rg_path: str, root: Path, pattern: str, *, glob: str | None,
                max_results: int, context: int, multiline: bool) -> list[dict]:
        import subprocess
        cmd = [rg_path, "--no-heading", "--line-number", "--color=never",
               "--max-count", str(max_results)]
        if context:
            cmd.extend(["-C", str(context)])
        if multiline:
            cmd.extend(["--multiline", "--multiline-dotall"])
        if glob:
            cmd.extend(["--glob", glob])
        cmd.extend([pattern, str(root)])

        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=15,
            encoding="utf-8", errors="replace",
        )
        results: list[dict] = []
        for line in proc.stdout.splitlines():
            if not line.strip():
                continue
            parts = line.split(":", 2)
            if len(parts) < 3:
                continue
            try:
                rel = Path(parts[0]).relative_to(root).as_posix()
            except ValueError:
                rel = parts[0]
            results.append({
                "path": rel,
                "line": int(parts[1]),
                "snippet": parts[2].strip(),
            })
            if len(results) >= max_results:
                break
        return results

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

    @staticmethod
    def _format_tree(items: list[dict]) -> str:
        """Format flat item list into a readable indented tree string."""
        if not items:
            return "(empty)"
        lines: list[str] = []
        for item in items:
            if item.get("type") == "truncated":
                lines.append(f"  ... ({item.get('note', 'truncated')})")
                break
            d = item["depth"]
            name = item["path"].split("/")[-1] if "/" in item["path"] else item["path"]
            is_dir = item["type"] == "dir"
            suffix = "/" if is_dir else ""
            indent = "  " * d
            lines.append(f"{indent}{name}{suffix}")
        return "\n".join(lines)

    _SKIP_DIRS = {".git", "__pycache__", ".venv", "node_modules", ".mypy_cache",
                   ".pytest_cache", ".ruff_cache", ".tox", ".eggs", "logs",
                   ".jarvis", ".claude", "codex", ".workbuddy"}
    _SKIP_EXT = {'.pyc', '.pyo', '.pyd', '.dll', '.so', '.exe', '.bin',
                 '.zip', '.tar', '.gz', '.7z', '.png', '.jpg', '.jpeg',
                 '.gif', '.ico', '.pdf', '.mp3', '.mp4', '.avi', '.wav',
                 '.ttf', '.woff', '.woff2', '.eot', '.db', '.sqlite',
                 '.sqlite3', '.jar', '.class', '.o', '.a', '.obj', '.lib'}

    @classmethod
    def _iter_text_files(cls, root: Path) -> Iterable[Path]:
        stack = [root]
        while stack:
            d = stack.pop()
            try:
                entries = list(d.iterdir())
            except (OSError, PermissionError):
                continue
            for entry in entries:
                if entry.is_dir():
                    if entry.name in cls._SKIP_DIRS:
                        continue
                    stack.append(entry)
                elif entry.is_file():
                    if entry.suffix.lower() in cls._SKIP_EXT:
                        continue
                    yield entry

