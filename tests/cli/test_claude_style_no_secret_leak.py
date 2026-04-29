"""Test that CLI does not leak secrets."""

import os
import subprocess
import sys

import pytest


def run_cli(*args, input_text=None, timeout=25, env=None):
    """Helper to run jarvis CLI command."""
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    
    # Add UTF-8 encoding settings for Windows
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


class TestNoSecretLeakInConfig:
    """Test that secrets are not leaked in config output."""

    def test_config_no_api_key_leak(self, monkeypatch):
        """Config should not leak API keys."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-1234567890")
        result = run_cli("config", "--show")
        output = result.stdout + result.stderr
        assert "sk-test-1234567890" not in output
        # Should be masked
        assert "sk-****" in output or "***" in output or "MASKED" in output

    def test_config_no_token_leak(self, monkeypatch):
        """Config should not leak tokens."""
        monkeypatch.setenv("JARVIS_TOKEN", "secret-token-12345")
        result = run_cli("config", "--show")
        output = result.stdout + result.stderr
        assert "secret-token-12345" not in output


class TestNoSecretLeakInShell:
    """Test that secrets are not leaked in shell mode."""

    def test_shell_config_no_leak(self, monkeypatch):
        """/config in shell should not leak secrets."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-1234567890")
        result = run_cli(input_text="/config\n/exit\n")
        output = result.stdout + result.stderr
        assert "sk-test-1234567890" not in output

    def test_shell_status_no_leak(self, monkeypatch):
        """/status should not leak secrets."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-1234567890")
        result = run_cli(input_text="/status\n/exit\n")
        output = result.stdout + result.stderr
        assert "sk-test-1234567890" not in output


class TestNoSecretLeakInOutput:
    """Test that secrets are not leaked in any output."""

    def test_tools_no_leak(self, monkeypatch):
        """`tools` command should not leak secrets."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-1234567890")
        result = run_cli("tools")
        output = result.stdout + result.stderr
        assert "sk-test-1234567890" not in output

    def test_help_no_leak(self, monkeypatch):
        """`--help` should not leak secrets."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-1234567890")
        result = run_cli("--help")
        output = result.stdout + result.stderr
        assert "sk-test-1234567890" not in output

    def test_shell_help_no_leak(self, monkeypatch):
        """/help in shell should not leak secrets."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-1234567890")
        result = run_cli(input_text="/help\n/exit\n")
        output = result.stdout + result.stderr
        assert "sk-test-1234567890" not in output


class TestMaskingWorks:
    """Test that masking functions work."""

    def test_mask_api_key(self):
        """API keys should be masked."""
        from jarvis.cli import _mask_secret_like
        
        test_text = "DEEPSEEK_API_KEY=sk-test-1234567890"
        masked = _mask_secret_like(test_text)
        assert "sk-test-1234567890" not in masked

    def test_mask_token(self):
        """Tokens should be masked."""
        from jarvis.cli import _mask_secret_like
        
        test_text = "token=secret-token-12345"
        masked = _mask_secret_like(test_text)
        assert "secret-token-12345" not in masked


class TestEnvVarNotPrinted:
    """Test that environment variables are not printed directly."""

    def test_no_env_var_leak(self, monkeypatch):
        """Environment variables should not be printed directly."""
        monkeypatch.setenv("JARVIS_SECRET_TEST", "super-secret-value-12345")
        result = run_cli(input_text="/exit\n")
        output = result.stdout + result.stderr
        assert "super-secret-value-12345" not in output
