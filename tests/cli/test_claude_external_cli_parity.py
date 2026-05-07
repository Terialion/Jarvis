"""Tests for Claude-style external CLI command behavior."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

from jarvis import cli as cli_mod

ROOT = Path(__file__).resolve().parents[2]


def run_cli(*args, input_text=None, timeout=25):
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONLEGACYWINDOWSSTDIO"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-m", "jarvis.cli", *args],
        input=input_text,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
        cwd=str(ROOT),
        env=env,
    )


def test_bare_cli_starts_shell():
    result = run_cli(input_text="/exit\n")
    out = result.stdout + result.stderr
    assert result.returncode == 0
    assert "Jarvis Code" in out


def test_help_flag_exits():
    result = run_cli("--help")
    out = result.stdout + result.stderr
    assert result.returncode == 0
    assert "usage" in out.lower()


def test_positional_prompt_routes_to_natural_response():
    result = run_cli("good evening")
    out = result.stdout + result.stderr
    assert result.returncode == 0
    assert "Task task_" not in out
    assert "Plan safe steps" not in out
    assert "Jarvis" in out
    assert "good evening" in out.lower() or "how can i help" in out.lower() or "i can" in out.lower()
    assert "Traceback" not in out


def test_print_prompt_repo_inspection_uses_non_interactive_renderer(monkeypatch):
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


def test_ask_prompt_oneshot_reuses_natural_path(monkeypatch):
    monkeypatch.setattr(cli_mod, "_load_local_env_file", lambda *_a, **_k: None)
    monkeypatch.setattr(cli_mod, "_write_cli_diagnostic", lambda *_a, **_k: None)
    called: dict[str, str] = {}

    def _fake_runner(prompt: str, *, output_mode: str = "default") -> int:
        called["prompt"] = prompt
        called["output_mode"] = output_mode
        return 0

    monkeypatch.setattr(cli_mod, "_run_non_interactive_with_mode", _fake_runner)
    monkeypatch.setattr("sys.argv", ["python", "--ask", "Inspect this repo. Do not modify files.", "--output", "quiet"])
    assert cli_mod.main() == 0
    assert called["prompt"] == "Inspect this repo. Do not modify files."
    assert called["output_mode"] == "quiet"


def test_resume_flags_controlled():
    latest = run_cli("-c")
    assert latest.returncode == 0
    assert "No previous session found." in (latest.stdout + latest.stderr)
    by_id = run_cli("-r", "not-found")
    assert by_id.returncode == 0
    assert "Session not found" in (by_id.stdout + by_id.stderr)
