"""Safety Guard module for Jarvis Core Phase 1."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter

from .result import error_result, ok_result


class SafetyGuard:
    """Minimal safety policies for command and write actions."""

    def __init__(self, forbidden_actions: list[str] | None = None) -> None:
        self._blocked_tokens = [
            "rm -rf",
            "del /f /s /q",
            "format ",
            "shutdown",
            "reboot",
            "mkfs",
        ]
        self._confirm_tokens = [
            "git push",
            "git reset",
            "pip install",
            "npm install",
            "poetry add",
        ]
        self._confirm_write_names = {
            ".env",
            ".env.local",
            "secrets.yml",
            "secrets.yaml",
            "credentials.json",
        }
        self._blocked_tokens = [self._normalize_rule_token(token) for token in self._blocked_tokens]
        if forbidden_actions:
            self.apply_rules({"forbidden_actions": forbidden_actions})

    @classmethod
    def from_rules(cls, rules: dict | None) -> "SafetyGuard":
        guard = cls()
        guard.apply_rules(rules or {})
        return guard

    def apply_rules(self, rules: dict) -> None:
        forbidden_actions = rules.get("forbidden_actions") or []
        for action in forbidden_actions:
            token = self._normalize_rule_token(str(action))
            if token and token not in self._blocked_tokens:
                self._blocked_tokens.append(token)

    def validate_command(self, command: str, cwd: str) -> dict:
        started = perf_counter()
        if not command or not cwd:
            return error_result(
                "COMMON_INVALID_INPUT",
                "command and cwd are required",
                {"command": command, "cwd": cwd},
                started,
            )
        cwd_path = Path(cwd)
        if not cwd_path.exists() or not cwd_path.is_dir():
            return error_result(
                "CMD_INVALID_CWD",
                f"Invalid cwd: {cwd}",
                {"cwd": cwd},
                started,
            )

        cmd = self._normalize_command_for_match(command)
        if any(token and token in cmd for token in self._blocked_tokens):
            return ok_result(
                {
                    "allowed": False,
                    "reason_code": "SAFE_COMMAND_BLOCKED",
                    "needs_confirmation": False,
                },
                started,
            )

        if any(token in cmd for token in self._confirm_tokens):
            return ok_result(
                {
                    "allowed": True,
                    "reason_code": "SAFE_CONFIRM_REQUIRED",
                    "needs_confirmation": True,
                },
                started,
            )

        return ok_result(
            {"allowed": True, "reason_code": "SAFE_ALLOWED", "needs_confirmation": False},
            started,
        )

    def validate_write(self, path: str, project_root: str) -> dict:
        started = perf_counter()
        if not path or not project_root:
            return error_result(
                "COMMON_INVALID_INPUT",
                "path and project_root are required",
                {"path": path, "project_root": project_root},
                started,
            )
        root = Path(project_root).resolve()
        if not root.exists() or not root.is_dir():
            return error_result(
                "REPO_INVALID_ROOT",
                f"Invalid project root: {project_root}",
                {"project_root": project_root},
                started,
            )
        target = Path(path).resolve()
        if not self._is_within_root(target, root):
            return ok_result(
                {
                    "allowed": False,
                    "reason_code": "SAFE_WRITE_OUT_OF_SCOPE",
                    "needs_confirmation": False,
                },
                started,
            )

        if target.name.lower() in self._confirm_write_names:
            return ok_result(
                {
                    "allowed": True,
                    "reason_code": "SAFE_CONFIRM_REQUIRED",
                    "needs_confirmation": True,
                },
                started,
            )

        return ok_result(
            {"allowed": True, "reason_code": "SAFE_ALLOWED", "needs_confirmation": False},
            started,
        )

    @staticmethod
    def _is_within_root(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    @classmethod
    def _normalize_rule_token(cls, raw: str) -> str:
        token = (raw or "").strip()
        token = cls._strip_wrapping_quotes(token)
        token = cls._collapse_spaces(token).lower()
        token = cls._strip_common_prefixes(token)
        return token

    @classmethod
    def _normalize_command_for_match(cls, command: str) -> str:
        cmd = cls._collapse_spaces((command or "").strip().lower())
        cmd = cls._strip_common_prefixes(cmd)
        return cmd

    @staticmethod
    def _strip_wrapping_quotes(text: str) -> str:
        value = text.strip()
        while len(value) >= 2 and ((value[0] == value[-1]) and value[0] in {"'", '"'}):
            value = value[1:-1].strip()
        return value

    @staticmethod
    def _collapse_spaces(text: str) -> str:
        return " ".join((text or "").split())

    @classmethod
    def _strip_common_prefixes(cls, text: str) -> str:
        value = text.strip()
        prefixes = [
            "bash -lc ",
            "sh -c ",
            "cmd /c ",
            "powershell -command ",
            "pwsh -command ",
            "sudo ",
        ]
        changed = True
        while changed:
            changed = False
            for prefix in prefixes:
                if value.startswith(prefix):
                    value = value[len(prefix) :].strip()
                    changed = True
                    break
        value = cls._strip_wrapping_quotes(value)
        value = cls._collapse_spaces(value)
        return value
