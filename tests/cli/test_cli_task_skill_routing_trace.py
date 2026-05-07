from __future__ import annotations

from jarvis import cli as cli_mod


def test_cli_non_interactive_repo_inspection_is_not_task_trace(monkeypatch):
    monkeypatch.setattr(cli_mod, "_load_local_env_file", lambda *_a, **_k: None)
    monkeypatch.setattr(cli_mod, "_write_cli_diagnostic", lambda *_a, **_k: None)
    called: dict[str, str] = {}

    def _fake_runner(prompt: str, *, output_mode: str = "default") -> int:
        called["prompt"] = prompt
        called["output_mode"] = output_mode
        return 0

    monkeypatch.setattr(cli_mod, "_run_non_interactive_with_mode", _fake_runner)
    monkeypatch.setattr(
        "sys.argv",
        ["python", "-p", "Choose the best skill for inspecting this repo. Do not modify files."],
    )
    assert cli_mod.main() == 0
    assert called["prompt"] == "Choose the best skill for inspecting this repo. Do not modify files."
    assert called["output_mode"] == "default"
