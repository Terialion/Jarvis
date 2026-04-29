import json
from argparse import Namespace

from jarvis import cli as cli_mod
from src.jarvis.api.server import JarvisApiState, route_request


class _Adapter:
    def __init__(self):
        self.state = JarvisApiState()
        self.last_task_id = None

    def _http_json(self, method, path, body=None):
        status, payload = route_request(self.state, method, path, body)
        data = payload.get("data")
        class _Res:
            ok = status == 200 and payload.get("ok") is True
            source = "api"
            error = ""
        res = _Res()
        res.data = data
        return res

    def create_task(self, prompt):
        res = self._http_json("POST", "/api/tasks", {"input": prompt, "mode": "safe", "require_approval": False})
        if res.ok and isinstance(res.data, dict):
            self.last_task_id = res.data.get("task_id")
        return res

    def get_task(self, task_id):
        return self._http_json("GET", f"/api/tasks/{task_id}")

    def get_task_events(self, task_id):
        return self._http_json("GET", f"/api/tasks/{task_id}/events")


def test_cli_task_run_emits_skill_selection(monkeypatch, capsys):
    adapter = _Adapter()
    monkeypatch.setattr(cli_mod, "_get_adapter", lambda api_base=None: adapter)

    run_args = Namespace(
        task_cmd="run",
        input="Inspect this repo structure with skill selection",
        mode="safe",
        safe=True,
        allow_code_changes=False,
        max_commands=3,
        max_files_changed=0,
        require_approval=False,
        api_base="http://127.0.0.1:8765",
    )
    assert cli_mod.cmd_task(run_args) == 0
    output = capsys.readouterr().out
    payload = json.loads(output)
    task_id = payload["task_id"]

    events_args = Namespace(task_cmd="events", task_id=task_id, api_base="http://127.0.0.1:8765")
    assert cli_mod.cmd_task(events_args) == 0
    events_out = capsys.readouterr().out
    events_payload = json.loads(events_out)
    event_types = [event["type"] for event in events_payload]
    assert "skill.selected" in event_types
    assert "skill.execution.dry_run" in event_types

