import json
import os
import sys
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from jarvis.core import (
    CheckpointManager,
    CommandRunner,
    ControlSurface,
    FailureAnalyzer,
    FileEditor,
    RepoReader,
    SafetyGuard,
    TaskRuntime,
    TestRunner,
    bind_gateway,
    make_handler,
)
from jarvis.core.react_readiness import HeavyReActConfig, HeavyReActRuntime


def _build_runtime(project_root: Path, *, config: HeavyReActConfig | None = None, guarded: bool = False) -> tuple[HeavyReActRuntime, TaskRuntime]:
    task_runtime = TaskRuntime()
    safety = SafetyGuard() if guarded else None
    editor = FileEditor(project_root=str(project_root), safety_guard=safety)
    runner = CommandRunner(safety_guard=safety)
    runtime = HeavyReActRuntime(
        project_root=str(project_root),
        task_runtime=task_runtime,
        repo_reader=RepoReader(),
        file_editor=editor,
        command_runner=runner,
        test_runner=TestRunner(test_commands=['python -c "print(\"ok\")"']),
        failure_analyzer=FailureAnalyzer(),
        checkpoint_manager=CheckpointManager(task_runtime),
        config=config,
    )
    return runtime, task_runtime


def _read_json(url: str, headers: dict | None = None) -> dict:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=6) as resp:  # nosec B310
        return json.loads(resp.read().decode("utf-8"))


def test_operator_e2e_success_and_retry_paths(tmp_path: Path) -> None:
    target = tmp_path / "sample.py"
    target.write_text("def calc():\n    return 1\n", encoding="utf-8")
    verifier = tmp_path / "verify_sample.py"
    verifier.write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "text = Path('sample.py').read_text(encoding='utf-8')\n"
        "sys.exit(0 if 'return 2' in text else 1)\n",
        encoding="utf-8",
    )

    runtime, task_runtime = _build_runtime(tmp_path, config=HeavyReActConfig(max_steps=8, retry_same_plan_limit=2, retry_replan_limit=1))
    runtime.run(
        task_input="success run",
        title="success",
        plan_template=[
            {"tool": "repo_reader.search_symbol", "symbol": "return 1"},
            {"tool": "file_editor.replace_text", "old": "return 1", "new": "return 2"},
            {"tool": "test_runner.run_test", "command": "python verify_sample.py"},
        ],
    )

    flag = tmp_path / "retry.flag"
    flaky_cmd = (
        f'python -c "import pathlib,sys; p=pathlib.Path(r\"{flag}\"); '
        'exists=p.exists(); p.write_text(\"x\"); sys.exit(0 if exists else 1)"'
    )
    runtime.run(
        task_input="retry run",
        title="retry",
        plan_template=[
            {"tool": "command_runner.run", "command": flaky_cmd},
            {"tool": "test_runner.run_test", "command": 'python -c "import sys; sys.exit(0)"'},
        ],
    )

    surface = ControlSurface(task_runtime, CheckpointManager(task_runtime), project_root=str(tmp_path))
    gateway = bind_gateway(task_runtime=task_runtime, control_surface=surface, project_root=str(tmp_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(surface, read_token="op-token", gateway=gateway))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[0], server.server_address[1]
    base = f"http://{host}:{port}"
    headers = {"Authorization": "Bearer op-token"}

    try:
        dashboard = _read_json(f"{base}/operator/dashboard", headers=headers)
        runs = _read_json(f"{base}/operator/runs?limit=10", headers=headers)
        assert dashboard["ok"] is True
        assert runs["ok"] is True
        assert runs["data"]["count"] >= 2
        first_run_id = runs["data"]["items"][0]["run_id"]
        detail = _read_json(f"{base}/operator/run/{first_run_id}", headers=headers)
        trace = _read_json(f"{base}/operator/run/{first_run_id}/trace", headers=headers)
        skills = _read_json(f"{base}/operator/run/{first_run_id}/skills", headers=headers)
        tools = _read_json(f"{base}/operator/run/{first_run_id}/tools", headers=headers)
        stop = _read_json(f"{base}/operator/run/{first_run_id}/stop", headers=headers)
        assert detail["ok"] is True
        assert trace["ok"] is True and trace["data"]["count"] >= 1
        assert skills["ok"] is True
        assert tools["ok"] is True and tools["data"]["count"] >= 1
        assert stop["ok"] is True
    finally:
        server.shutdown()
        server.server_close()


def test_operator_e2e_failure_fallback_path(tmp_path: Path) -> None:
    runtime, task_runtime = _build_runtime(
        tmp_path,
        config=HeavyReActConfig(max_steps=4, max_failures=1, retry_same_plan_limit=0, retry_replan_limit=0),
    )
    runtime.run(task_input="fallback run", title="fallback", plan_template=[{"tool": "unknown.tool"}])

    surface = ControlSurface(task_runtime, CheckpointManager(task_runtime), project_root=str(tmp_path))
    gateway = bind_gateway(task_runtime=task_runtime, control_surface=surface, project_root=str(tmp_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(surface, read_token="op-token", gateway=gateway))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[0], server.server_address[1]
    base = f"http://{host}:{port}"
    headers = {"Authorization": "Bearer op-token"}

    try:
        runs = _read_json(f"{base}/operator/runs?limit=10&success=false", headers=headers)
        assert runs["ok"] is True
        assert runs["data"]["count"] >= 1
        run_id = runs["data"]["items"][0]["run_id"]
        stop = _read_json(f"{base}/operator/run/{run_id}/stop", headers=headers)
        review_summary = _read_json(f"{base}/operator/review/summary", headers=headers)
        gate_summary = _read_json(f"{base}/operator/gate/summary", headers=headers)
        assert stop["ok"] is True
        assert stop["data"]["stop_reason"] in {"repeated_failure_stop", "max_steps_stop", "no_progress_stop"}
        assert stop["data"]["fallback_type"] in {"fallback_to_human_review", "fallback_to_summary"}
        assert review_summary["ok"] is True
        assert gate_summary["ok"] is True
    finally:
        server.shutdown()
        server.server_close()
