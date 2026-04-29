"""Phase 3 lightweight real task flow bootstrap for review/control consumption."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter

from .checkpoint_manager import CheckpointManager
from .command_runner import CommandRunner
from .repo_reader import RepoReader
from .result import error_result, ok_result
from .runtime_snapshot import save_runtime_snapshot
from .task_runtime import TaskRuntime
from .test_runner import TestRunner


def run_real_task_flow(
    *,
    project_root: str,
    snapshot_path: str | None = None,
    task_title: str = "phase3 real review flow",
) -> dict:
    started = perf_counter()
    root = Path(project_root).resolve()
    if not root.exists() or not root.is_dir():
        return error_result(
            "REPO_INVALID_ROOT",
            f"Invalid project root: {project_root}",
            {"project_root": project_root},
            started,
        )

    runtime = TaskRuntime()
    task_created = runtime.create_task(project_id=str(root), title=task_title)
    if not task_created["ok"]:
        return task_created
    task = task_created["data"]
    task_id = task["task_id"]
    runtime.set_status(task_id, "running")

    reader = RepoReader()
    command_runner = CommandRunner()
    test_runner = TestRunner(test_commands=['python -c "print(\'phase3_real_test_ok\')"'])
    checkpoints = CheckpointManager(runtime)

    search = reader.search_symbol(str(root), "def ", max_results=5)
    if not search["ok"]:
        search = reader.search_files(str(root), ".py", max_results=5)
    runtime.add_step(task_id, "repo_read.search", {"ok": search["ok"], "query": "def "})

    cmd = command_runner.run('python -c "print(\'phase3_real_command_ok\')"', cwd=str(root), timeout_s=20)
    runtime.attach_command_run(task_id, cmd["data"] if cmd["ok"] else {"ok": False, "error": cmd.get("error")})
    runtime.add_step(task_id, "run_command", {"ok": cmd["ok"]})

    test = test_runner.run_test(None, cwd=str(root), timeout_s=30)
    runtime.attach_test_run(task_id, test["data"] if test["ok"] else {"passed": False, "error": test.get("error")})
    runtime.add_step(task_id, "run_test", {"ok": test["ok"], "passed": (test.get("data") or {}).get("passed")})

    ckpt = checkpoints.create_checkpoint(task_id, "phase3-bootstrap")
    checkpoint_id = (ckpt.get("data") or {}).get("checkpoint_id")

    summary = (
        f"phase3 bootstrap done | repo_read_ok={search['ok']} | "
        f"command_ok={cmd['ok']} | test_ok={test['ok']}"
    )
    runtime.finalize(task_id, summary)

    target_snapshot = snapshot_path or str(root / ".jarvis" / "state" / "runtime_snapshot.latest.json")
    saved = save_runtime_snapshot(runtime, target_snapshot)
    if not saved["ok"]:
        return saved
    return ok_result(
        {
            "task_id": task_id,
            "checkpoint_id": checkpoint_id,
            "snapshot_path": target_snapshot,
            "summary": summary,
        },
        started,
    )
