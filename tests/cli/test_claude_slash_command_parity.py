"""Tests for Claude-style slash command routing parity."""

import json
import subprocess
import sys


def run_cli(*args, input_text=None, timeout=25):
    return subprocess.run(
        [sys.executable, "-m", "jarvis.cli", *args],
        input=input_text,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
        cwd="d:/jarvis",
    )


def test_p0_commands_recognized():
    result = run_cli(input_text="/help\n/commands\n/skills\n/tools\n/status\n/exit\n")
    out = result.stdout + result.stderr
    assert result.returncode == 0
    assert "Commands:" in out
    assert "Jarvis Command Map" in out


def test_p1_skeleton_and_p2_unsupported():
    result = run_cli(input_text="/compact\n/loop\n/exit\n")
    out = result.stdout + result.stderr
    assert "status: skeleton" in out
    assert "status: unsupported" in out


def test_unknown_command_suggests_close_match():
    result = run_cli(input_text="/commads\n/exit\n")
    out = result.stdout + result.stderr
    assert "Unknown command" in out
    assert "/commands" in out


def test_commands_json_valid():
    result = run_cli("commands", "--json")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert isinstance(payload, list) and payload
    assert any(row.get("name") == "/help" for row in payload)

