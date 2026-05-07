from __future__ import annotations

from pathlib import Path
import subprocess
import sys

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


def test_greeting_is_conversational_not_task_trace():
    result = run_cli(input_text="hello\n/exit\n")
    output = result.stdout + result.stderr
    assert result.returncode == 0
    assert "Jarvis" in output
    assert "Task task_" not in output
    assert "skill.registry.loaded" not in output
    assert "mock-safe" not in output
    assert "Traceback" not in output


def test_capability_question_is_natural_response():
    result = run_cli(input_text="what can you do\n/exit\n")
    output = result.stdout + result.stderr
    assert result.returncode == 0
    assert "/help" in output or "skills" in output.lower() or "skill" in output.lower()
    assert "Task task_" not in output
    assert "mock-safe" not in output


def test_repo_inspection_not_task_mode():
    result = run_cli(input_text="who are you\n/exit\n")
    output = result.stdout + result.stderr
    assert result.returncode == 0
    assert "Task task_" not in output
    assert "pytest -q" not in output or "I can inspect repositories" in output
    assert "Traceback" not in output
