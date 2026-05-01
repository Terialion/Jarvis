from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from ...cli_command_map import resolve_command

_URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
_WINDOWS_PATH_RE = re.compile(r"^[A-Za-z]:[\\/]")
_SENSITIVE_HINT_TOKENS = (".env", ".ssh", "id_rsa", "id_ed25519", "credential", "token", "secret", ".pem", ".key")
_UNIX_ABSOLUTE_PREFIXES = (
    "/users/",
    "/home/",
    "/etc/",
    "/tmp/",
    "/var/",
    "/opt/",
    "/srv/",
    "/mnt/",
    "/proc/",
    "/dev/",
    "/private/",
    "/usr/",
)


@dataclass
class SlashInfo:
    is_slash_command: bool = False
    command_name: str | None = None
    raw_args: str = ""
    args_tokens: list[str] = field(default_factory=list)
    is_unknown_command: bool = False
    looks_like_path: bool = False


@dataclass
class InputEnvelope:
    raw_text: str
    normalized_text: str
    language_hint: Literal["zh", "en", "unknown"]
    is_empty: bool
    slash: SlashInfo
    has_url: bool
    urls: list[str]
    path_hints: list[str]
    sensitive_hints: list[str]
    workspace_root: Path | None
    session_id: str | None


def build_input_envelope(
    raw_text: str,
    *,
    workspace_root: Path | None = None,
    session_id: str | None = "cli_shell",
) -> InputEnvelope:
    text = str(raw_text or "")
    normalized = " ".join(text.strip().split())
    root = (workspace_root or Path.cwd()).resolve() if workspace_root is not None or Path.cwd() else None
    urls = _URL_RE.findall(normalized)
    path_hints = _collect_path_hints(normalized)
    slash = _parse_slash(normalized)
    if slash.looks_like_path and normalized and normalized not in path_hints:
        path_hints.append(normalized)
    sensitive_hints = sorted({token for token in _SENSITIVE_HINT_TOKENS if token in normalized.lower()})
    return InputEnvelope(
        raw_text=text,
        normalized_text=normalized,
        language_hint=_detect_language(normalized),
        is_empty=not bool(normalized),
        slash=slash,
        has_url=bool(urls),
        urls=urls,
        path_hints=path_hints,
        sensitive_hints=sensitive_hints,
        workspace_root=root,
        session_id=session_id,
    )


def _parse_slash(text: str) -> SlashInfo:
    if not text.startswith("/"):
        return SlashInfo()
    if _looks_like_unix_absolute_path(text):
        return SlashInfo(is_slash_command=False, looks_like_path=True)
    first, _, rest = text.partition(" ")
    command_name = first[1:].strip().lower() or None
    raw_args = rest.strip()
    args_tokens = [token for token in raw_args.split() if token]
    known = False
    if command_name:
        known = resolve_command(f"/{command_name}") is not None or resolve_command(command_name) is not None
    return SlashInfo(
        is_slash_command=True,
        command_name=command_name,
        raw_args=raw_args,
        args_tokens=args_tokens,
        is_unknown_command=bool(command_name) and not known,
        looks_like_path=False,
    )


def _detect_language(text: str) -> Literal["zh", "en", "unknown"]:
    if not text:
        return "unknown"
    if any("\u4e00" <= char <= "\u9fff" for char in text):
        return "zh"
    if any("a" <= char.lower() <= "z" for char in text):
        return "en"
    return "unknown"


def _collect_path_hints(text: str) -> list[str]:
    hints: list[str] = []
    candidate = text.strip()
    if not candidate:
        return hints
    low = candidate.lower()
    if _looks_like_unix_absolute_path(candidate) or _WINDOWS_PATH_RE.match(candidate):
        hints.append(candidate)
    elif any(token in candidate for token in (".py", ".md", ".json", ".yaml", ".yml", ".toml", ".txt")) and any(
        sep in candidate for sep in ("/", "\\")
    ):
        hints.append(candidate)
    elif any(low.startswith(prefix) for prefix in ("./", "../")):
        hints.append(candidate)
    return hints


def _looks_like_unix_absolute_path(text: str) -> bool:
    low = text.lower()
    if any(low.startswith(prefix) for prefix in _UNIX_ABSOLUTE_PREFIXES):
        return True
    if not text.startswith("/"):
        return False
    first, _, _rest = text.partition(" ")
    return "/" in first[1:]
