"""Git worktree manager — directory isolation bound to task IDs (s12)."""

from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any


_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,40}$")


class WorktreeManager:
    """Manage git worktrees in ``.jarvis/worktrees/``, bound to task IDs."""

    def __init__(
        self,
        repo_root: Path,
        tasks: Any = None,
        events: Any = None,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.worktrees_dir = self.repo_root / ".jarvis" / "worktrees"
        self.worktrees_dir.mkdir(parents=True, exist_ok=True)
        self.tasks = tasks  # PersistentTaskManager
        self.events = events  # EventBus
        self._git_available: bool | None = None

    # ── helpers ─────────────────────────────────────────────────────

    def _is_git_repo(self) -> bool:
        if self._git_available is not None:
            return self._git_available
        try:
            subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                capture_output=True, text=True, timeout=10, cwd=str(self.repo_root),
                check=True,
            )
            self._git_available = True
        except Exception:
            self._git_available = False
        return self._git_available

    def _run_git(self, args: list[str]) -> str:
        try:
            proc = subprocess.run(
                ["git"] + args,
                capture_output=True, text=True, timeout=120, cwd=str(self.repo_root),
            )
            if proc.returncode != 0:
                return f"git error: {proc.stderr.strip()}"
            return proc.stdout.strip()
        except subprocess.TimeoutExpired:
            return "git error: timeout"
        except Exception as e:
            return f"git error: {e}"

    def _index_path(self) -> Path:
        return self.worktrees_dir / "index.json"

    def _load_index(self) -> dict[str, Any]:
        path = self._index_path()
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {"worktrees": []}

    def _save_index(self, data: dict[str, Any]) -> None:
        self._index_path().write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _find(self, name: str) -> dict[str, Any] | None:
        index = self._load_index()
        for wt in index.get("worktrees", []):
            if wt["name"] == name:
                return wt
        return None

    def _validate_name(self, name: str) -> str | None:
        if not _NAME_RE.match(name):
            return f"invalid name: '{name}' (1-40 chars, alphanumeric + ._-)"
        return None

    # ── public API ──────────────────────────────────────────────────

    def create(
        self,
        name: str,
        task_id: str | None = None,
        base_ref: str = "HEAD",
    ) -> dict[str, Any]:
        if not self._is_git_repo():
            return {"ok": False, "error": "not a git repository"}

        err = self._validate_name(name)
        if err:
            return {"ok": False, "error": err}

        if self._find(name) is not None:
            return {"ok": False, "error": f"worktree '{name}' already exists"}

        wt_path = self.worktrees_dir / name
        branch = f"wt/{name}"

        if self.events:
            self.events.emit("worktree.create.before", worktree={"name": name, "path": str(wt_path)})

        result = self._run_git(["worktree", "add", "-b", branch, str(wt_path), base_ref])
        if result.startswith("git error"):
            if self.events:
                self.events.emit("worktree.create.failed", worktree={"name": name}, error=result)
            return {"ok": False, "error": result}

        entry = {
            "name": name,
            "path": str(wt_path),
            "branch": branch,
            "task_id": task_id,
            "status": "active",
            "created_at": time.time(),
        }

        index = self._load_index()
        index.setdefault("worktrees", []).append(entry)
        self._save_index(index)

        if task_id and self.tasks:
            self.tasks.bind_worktree(task_id, name)

        if self.events:
            self.events.emit("worktree.create.after", worktree=entry)

        return {"ok": True, "worktree": entry}

    def list_all(self) -> dict[str, Any]:
        index = self._load_index()
        return {"worktrees": index.get("worktrees", [])}

    def status(self, name: str) -> dict[str, Any]:
        if not self._is_git_repo():
            return {"ok": False, "error": "not a git repository"}
        wt = self._find(name)
        if wt is None:
            return {"ok": False, "error": f"worktree '{name}' not found"}
        output = subprocess.run(
            ["git", "status", "--short", "--branch"],
            capture_output=True, text=True, timeout=30,
            cwd=wt["path"],
        )
        return {"ok": True, "name": name, "status_output": output.stdout.strip()}

    def run(self, name: str, command: str) -> dict[str, Any]:
        wt = self._find(name)
        if wt is None:
            return {"ok": False, "error": f"worktree '{name}' not found"}
        if not wt["path"] or not Path(wt["path"]).exists():
            return {"ok": False, "error": f"worktree path missing: {wt['path']}"}
        try:
            proc = subprocess.run(
                command, shell=True, capture_output=True, text=True,
                timeout=300, cwd=wt["path"],
            )
            return {
                "ok": True,
                "name": name,
                "stdout": proc.stdout.strip(),
                "stderr": proc.stderr.strip(),
                "returncode": proc.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "command timeout"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def remove(
        self,
        name: str,
        force: bool = False,
        complete_task: bool = False,
    ) -> dict[str, Any]:
        if not self._is_git_repo():
            return {"ok": False, "error": "not a git repository"}
        wt = self._find(name)
        if wt is None:
            return {"ok": False, "error": f"worktree '{name}' not found"}

        if self.events:
            self.events.emit("worktree.remove.before", worktree={"name": name, "path": wt["path"]})

        args = ["worktree", "remove"]
        if force:
            args.append("--force")
        args.append(str(wt["path"]))

        result = self._run_git(args)
        if result.startswith("git error") and not force:
            if self.events:
                self.events.emit("worktree.remove.failed", worktree={"name": name}, error=result)
            return {"ok": False, "error": result}

        wt["status"] = "removed"
        index = self._load_index()
        index["worktrees"] = [
            w for w in index.get("worktrees", [])
            if w["name"] != name
        ]
        index.setdefault("worktrees", []).append(wt)
        self._save_index(index)

        if complete_task and wt.get("task_id") and self.tasks:
            self.tasks.update(wt["task_id"], status="completed")
            self.tasks.unbind_worktree(wt["task_id"])
            if self.events:
                self.events.emit("task.completed", task={"id": wt["task_id"]})

        if self.events:
            self.events.emit("worktree.remove.after", worktree=wt)

        return {"ok": True, "worktree": wt}

    def keep(self, name: str) -> dict[str, Any]:
        wt = self._find(name)
        if wt is None:
            return {"ok": False, "error": f"worktree '{name}' not found"}
        wt["status"] = "kept"
        index = self._load_index()
        for i, w in enumerate(index.get("worktrees", [])):
            if w["name"] == name:
                index["worktrees"][i] = wt
                break
        self._save_index(index)
        if self.events:
            self.events.emit("worktree.keep", worktree=wt)
        return {"ok": True, "worktree": wt}
