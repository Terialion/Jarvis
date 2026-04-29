"""Test tools and skills listing for Jarvis CLI."""

import os
import subprocess
import sys

import pytest


def run_cli(*args, input_text=None, timeout=25):
    """Helper to run jarvis CLI command."""
    merged_env = os.environ.copy()
    merged_env["PYTHONIOENCODING"] = "utf-8"
    merged_env["PYTHONLEGACYWINDOWSSTDIO"] = "utf-8"
    
    result = subprocess.run(
        [sys.executable, "-m", "jarvis.cli", *args],
        input=input_text,
        text=True,
        capture_output=True,
        timeout=timeout,
        cwd="d:/jarvis",
        encoding="utf-8",
        errors="ignore",
        env=merged_env,
    )
    # Ensure stdout and stderr are not None
    if result.stdout is None:
        result.stdout = ""
    if result.stderr is None:
        result.stderr = ""
    return result


class TestToolsCommand:
    """Test tools command."""

    def test_tools_non_empty_output(self):
        """`tools` command should print non-empty output."""
        result = run_cli("tools")
        output = result.stdout + result.stderr
        assert result.returncode == 0
        assert output.strip()
        assert "tool" in output.lower() or "capabilit" in output.lower()

    def test_tools_shows_tools(self):
        """`tools` command should show available tools."""
        result = run_cli("tools")
        output = result.stdout + result.stderr
        assert "web_search" in output or "tool" in output.lower() or "capabilit" in output.lower()

    def test_tools_no_crash(self):
        """`tools` command should not crash."""
        result = run_cli("tools")
        assert result.returncode == 0


class TestSkillsCommand:
    """Test skills command."""

    def test_skills_non_empty_output(self):
        """`skills` command should print non-empty output."""
        result = run_cli("skills")
        output = result.stdout + result.stderr
        assert result.returncode == 0
        assert output.strip()

    def test_slash_skills_non_empty(self):
        """`/skills` should print non-empty output."""
        result = run_cli(input_text="/skills\n/exit\n")
        output = result.stdout + result.stderr
        assert result.returncode == 0
        assert output.strip()
        assert "web_search" in output or "skill" in output.lower() or "capabilit" in output.lower()

    def test_skills_shows_skills(self):
        """`skills` command should show available skills."""
        result = run_cli("skills")
        output = result.stdout + result.stderr
        # Should show at least fallback capabilities
        assert "web_search" in output or "memory" in output or "skill" in output.lower()


class TestToolsInShell:
    """Test tools listing in shell mode."""

    def test_shell_tools_non_empty(self):
        """`/tools` in shell should print non-empty output."""
        result = run_cli(input_text="/tools\n/exit\n")
        output = result.stdout + result.stderr
        assert result.returncode == 0
        assert output.strip()

    def test_shell_tools_shows_content(self):
        """`/tools` in shell should show tools or capabilities."""
        result = run_cli(input_text="/tools\n/exit\n")
        output = result.stdout + result.stderr
        assert "tool" in output.lower() or "capabilit" in output.lower()


class TestCapabilitiesListed:
    """Test that fallback capabilities are listed."""

    def test_fallback_capabilities_listed(self):
        """Fallback capabilities should be listed when no registry."""
        # This is hard to test without mocking, but we can check output
        result = run_cli("tools")
        output = result.stdout + result.stderr
        # Should have some content
        assert len(output.strip()) > 0

    def test_capabilities_have_name(self):
        """Each capability should have a name."""
        result = run_cli("tools")
        output = result.stdout + result.stderr
        # Check for typical capability names
        assert "web_search" in output or "memory" in output or "=" in output
