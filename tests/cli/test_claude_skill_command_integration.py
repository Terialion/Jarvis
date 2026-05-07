"""CLI integration tests for Claude-style skill flows."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from jarvis import cli as cli_mod

ROOT = Path(__file__).resolve().parents[2]


def run_cli(*args, input_text=None, timeout=25):
    return subprocess.run(
        [sys.executable, "-m", "jarvis.cli", *args],
        input=input_text,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
        cwd=str(ROOT),
    )


def test_slash_skill_command_is_local():
    result = run_cli(input_text="/skill summarize_file README.md\n/exit\n")
    out = result.stdout + result.stderr
    assert result.returncode == 0
    assert "Skill command recognized" in out


def test_natural_language_repo_inspection_not_task(monkeypatch):
    monkeypatch.setattr(cli_mod, "_load_local_env_file", lambda *_a, **_k: None)
    monkeypatch.setattr(cli_mod, "_write_cli_diagnostic", lambda *_a, **_k: None)
    called: dict[str, str] = {}

    def _fake_runner(prompt: str, *, output_mode: str = "default") -> int:
        called["prompt"] = prompt
        called["output_mode"] = output_mode
        return 0

    monkeypatch.setattr(cli_mod, "_run_non_interactive_with_mode", _fake_runner)
    monkeypatch.setattr("sys.argv", ["python", "-p", "Inspect this repo. Do not modify files."])
    assert cli_mod.main() == 0
    assert called["prompt"] == "Inspect this repo. Do not modify files."
    assert called["output_mode"] == "default"
