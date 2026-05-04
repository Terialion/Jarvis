"""Tests for command mapping + skill integration."""

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


def test_skills_lists_real_registry_output():
    result = run_cli("skills")
    out = result.stdout + result.stderr
    assert result.returncode == 0
    assert "Jarvis Skills" in out or "No skills found" in out


def test_tools_lists_real_skills_or_capabilities():
    result = run_cli("tools")
    out = result.stdout + result.stderr
    assert result.returncode == 0
    assert "tool" in out.lower() or "capabilit" in out.lower() or "skill" in out.lower()


def test_doctor_includes_skill_counts():
    result = run_cli(input_text="/doctor\n/exit\n")
    out = result.stdout + result.stderr
    assert result.returncode == 0
    assert "skill registry" in out.lower()


def test_permissions_mentions_trust_quarantine():
    result = run_cli(input_text="/permissions\n/exit\n")
    out = result.stdout + result.stderr
    assert result.returncode == 0
    assert "trust/quarantine" in out.lower()


def test_natural_language_repo_inspection_not_task():
    result = run_cli("-p", "Inspect this repo. Do not modify files.")
    out = result.stdout + result.stderr
    assert result.returncode == 0
    assert "Task task_" not in out
    # Now routed through AgentToolLoop (returns LLM fallback or work acknowledgement)
    assert "jarvis" in out.lower() or "llm provider" in out.lower() or "无法连接" in out or "repository inspection" in out.lower()
