import json

from jarvis import cli as cli_mod


def test_old_state_file_remains_readable(tmp_path, monkeypatch):
    old_state = {
        "tasks": {
            "task_1": {
                "task_id": "task_1",
                "status": "completed",
            }
        },
        "approvals": {},
        "latest_task_id": "task_1",
    }
    state_path = tmp_path / "cli_coding_state.json"
    state_path.write_text(json.dumps(old_state), encoding="utf-8")
    monkeypatch.setattr(cli_mod, "_CLI_STATE_PATH", state_path)

    loaded = cli_mod._load_cli_coding_state()
    assert loaded["tasks"]["task_1"]["task_id"] == "task_1"
    assert loaded.get("schema_version")

    cli_mod._save_cli_coding_state(loaded)
    reloaded = cli_mod._load_cli_coding_state()
    assert reloaded["latest_task_id"] == "task_1"


def test_gc_and_prune_do_not_crash_on_minimal_state(tmp_path, monkeypatch):
    state_path = tmp_path / "cli_coding_state.json"
    state_path.write_text('{"tasks": {}, "approvals": {}, "latest_task_id": ""}', encoding="utf-8")
    monkeypatch.setattr(cli_mod, "_CLI_STATE_PATH", state_path)
    state = cli_mod._load_cli_coding_state()
    pruned = cli_mod._prune_approvals(state, status_filter="all-closed", older_than_days=0, apply_changes=False)
    gc = cli_mod._gc_tasks(state, older_than_days=14, keep_latest=20, apply_changes=False)
    assert isinstance(pruned, dict)
    assert isinstance(gc, dict)
