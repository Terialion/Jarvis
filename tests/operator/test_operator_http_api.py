import json
import os
import sys
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from jarvis.core import CheckpointManager, ControlSurface, TaskRuntime, bind_gateway, make_handler


def _seed_runtime(tmp_path: Path) -> tuple[ControlSurface, object]:
    runtime = TaskRuntime()
    task = runtime.create_task("operator_http", "operator task")["data"]
    task_id = task["task_id"]
    runtime.add_step(task_id, "react.step", {"step_number": 0})
    runtime.finalize(task_id, "done")
    runtime.tasks[task_id]["react_runs"] = [
        {
            "run_id": "react_run_success",
            "task_id": task_id,
            "state": "completed",
            "traces": [
                {
                    "step_number": 0,
                    "observation": {"payload": {"step_number": 0, "pending_plan_steps": 2, "task_status": "running"}},
                    "chosen_skill": "code_fix",
                    "chosen_tool": "repo_reader.search_symbol",
                    "action_input": {"tool": "repo_reader.search_symbol", "symbol": "x"},
                    "action_result": {"ok": True, "data": {"matches": []}},
                    "check_result": {"passed": True, "outcome": "success"},
                }
            ],
            "stop_record": {"reason": "success", "detail": {}},
            "retries": 0,
            "fallback": {"mode": "none", "detail": None},
            "skill_eval": {"total_steps": 1},
            "duration_ms": 10,
        }
    ]
    runtime.tasks[task_id]["latest_react_run_id"] = "react_run_success"
    surface = ControlSurface(runtime, CheckpointManager(runtime), project_root=str(tmp_path))
    gateway = bind_gateway(task_runtime=runtime, control_surface=surface, project_root=str(tmp_path))
    return surface, gateway


def _read_json(url: str, headers: dict | None = None) -> tuple[dict, dict]:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=5) as resp:  # nosec B310
        return json.loads(resp.read().decode("utf-8")), dict(resp.headers.items())


def test_operator_http_routes_and_request_ids(tmp_path: Path) -> None:
    surface, gateway = _seed_runtime(tmp_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(surface, read_token="op-token", gateway=gateway))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[0], server.server_address[1]
    base = f"http://{host}:{port}"

    try:
        headers = {
            "Authorization": "Bearer op-token",
            "X-Request-Id": "rid_operator_1",
            "X-Correlation-Id": "corr_operator_1",
        }
        dashboard, _ = _read_json(f"{base}/operator/dashboard", headers=headers)
        runs, _ = _read_json(f"{base}/operator/runs?limit=5", headers=headers)
        run_detail, _ = _read_json(f"{base}/operator/run/react_run_success", headers=headers)
        trace, _ = _read_json(f"{base}/operator/run/react_run_success/trace", headers=headers)
        skills, _ = _read_json(f"{base}/operator/run/react_run_success/skills", headers=headers)
        tools, _ = _read_json(f"{base}/operator/run/react_run_success/tools", headers=headers)
        stop, headers_out = _read_json(f"{base}/operator/run/react_run_success/stop", headers=headers)
        gateway_summary, _ = _read_json(f"{base}/operator/gateway/summary", headers=headers)
        channels_summary, _ = _read_json(f"{base}/operator/channels/summary", headers=headers)
        nodes_summary, _ = _read_json(f"{base}/operator/nodes/summary", headers=headers)
        review_summary, _ = _read_json(f"{base}/operator/review/summary", headers=headers)
        gate_summary, _ = _read_json(f"{base}/operator/gate/summary", headers=headers)

        assert dashboard["ok"] is True
        assert runs["ok"] is True and runs["data"]["count"] == 1
        assert run_detail["ok"] is True and run_detail["data"]["run"]["run_id"] == "react_run_success"
        assert trace["ok"] is True and trace["data"]["count"] == 1
        assert skills["ok"] is True and isinstance(skills["data"]["items"], list)
        assert tools["ok"] is True and tools["data"]["count"] == 1
        assert stop["ok"] is True and stop["data"]["stop_reason"] == "success"
        assert gateway_summary["ok"] is True
        assert channels_summary["ok"] is True
        assert nodes_summary["ok"] is True
        assert review_summary["ok"] is True
        assert gate_summary["ok"] is True
        assert stop["meta"]["request_id"] == "rid_operator_1"
        assert stop["meta"]["correlation_id"] == "corr_operator_1"
        assert headers_out.get("X-Request-Id") == "rid_operator_1"
    finally:
        server.shutdown()
        server.server_close()


def test_operator_page_html_renders(tmp_path: Path) -> None:
    surface, gateway = _seed_runtime(tmp_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(surface, read_token="op-token", gateway=gateway))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[0], server.server_address[1]
    base = f"http://{host}:{port}"
    try:
        req = urllib.request.Request(f"{base}/operator-page", headers={"Authorization": "Bearer op-token"})
        with urllib.request.urlopen(req, timeout=5) as resp:  # nosec B310
            html = resp.read().decode("utf-8")
        assert "Jarvis Operator Surface (Minimal)" in html
        assert "Run List" in html
        assert "Stop / Approval / Fallback" in html
    finally:
        server.shutdown()
        server.server_close()
