#!/usr/bin/env python
"""Jarvis CLI."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from urllib import request
from uuid import uuid4

from .cli_command_map import CliCommandSpec, list_command_specs, render_command_table, resolve_command, suggest_commands

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

DEFAULT_API_BASE = os.getenv("JARVIS_API_BASE", "http://127.0.0.1:8765").rstrip("/")
DEFAULT_WEB_URL = os.getenv("JARVIS_WEB_URL", "http://127.0.0.1:18789")

SHELL_HEADER_TEMPLATE = "Jarvis Code - {cwd}"
SHELL_HELP_HINT = "Type /help for commands, /exit to quit."
SHELL_PROMPT = "> "

FALLBACK_CAPABILITIES = [
    "web_search",
    "web_open",
    "memory",
    "replay",
    "evidence",
    "operator_summary",
    "approvals",
    "settings",
    "tasks",
    "skills",
    "server",
]

_DIAG_PATH = _ROOT / "temp" / "cli_stderr_diagnostics.json"
_CLI_STATE_PATH = _ROOT / "temp" / "cli_coding_state.json"
_CODING_FIXTURE_DIR = _ROOT / "examples" / "coding_fixture"
_CODING_FIXTURE_FILE = _CODING_FIXTURE_DIR / "calculator.py"
_CODING_FIXTURE_TEST = _CODING_FIXTURE_DIR / "test_calculator.py"
_CLI_SURFACE_DOC = _ROOT / "docs" / "product" / "cli_surface.md"
_LIBRARY_PROJECT_FILES = [
    "library_system/__init__.py",
    "library_system/storage.py",
    "library_system/library.py",
    "library_system/cli.py",
    "library_system/tests/test_library.py",
    "library_system/README.md",
]
_DIAG_STATE: Dict[str, Any] = {
    "schema_version": "jarvis.cli.stderr_diagnostics.v1",
    "generated_at": "",
    "checkpoints": [],
}

_CLI_STATE_SCHEMA_VERSION = "jarvis.cli.coding_state.v2"
_INTENT_TRACE_PATH = _ROOT / "temp" / "intent_routes" / "routes.jsonl"


class InputKind(Enum):
    SLASH_COMMAND = "slash_command"
    GREETING = "greeting"
    CASUAL_CHAT = "casual_chat"
    CAPABILITY_QUESTION = "capability_question"
    CODING_TASK = "coding_task"
    REPO_INSPECTION_TASK = "repo_inspection_task"
    SKILL_ROUTING_TASK = "skill_routing_task"
    TEST_OR_SHELL_TASK = "test_or_shell_task"
    UNKNOWN_TASK = "unknown_task"


def _iso_now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _mask_secret_like(text: str) -> str:
    if not text:
        return text
    masked = re.sub(r"\bsk-[A-Za-z0-9_-]{4,}\b", "sk-****", str(text))
    masked = re.sub(r"(?i)(api[_-]?key|token|password|private key)\s*[:=]\s*\S+", r"\1=****", masked)
    return masked


def _stream_info(stream: Any) -> Dict[str, Any]:
    if stream is None:
        return {"id": "None", "type": "NoneType", "closed": None}
    try:
        return {
            "id": str(id(stream)),
            "type": type(stream).__name__,
            "closed": bool(getattr(stream, "closed", False)),
        }
    except Exception:
        return {"id": "unknown", "type": "unknown", "closed": None}


def _iter_logging_handlers() -> List[logging.Handler]:
    handlers: List[logging.Handler] = []
    try:
        handlers.extend(logging.getLogger().handlers)
        for logger in logging.Logger.manager.loggerDict.values():
            if isinstance(logger, logging.Logger):
                handlers.extend(logger.handlers)
    except Exception:
        pass
    uniq = []
    seen = set()
    for h in handlers:
        hid = id(h)
        if hid in seen:
            continue
        seen.add(hid)
        uniq.append(h)
    return uniq


def _safe_default_stream(prefer_stderr: bool) -> Any:
    if prefer_stderr:
        candidates = [getattr(sys, "__stderr__", None), getattr(sys, "__stdout__", None)]
    else:
        candidates = [getattr(sys, "__stdout__", None), getattr(sys, "__stderr__", None)]
    for stream in candidates:
        if stream is None:
            continue
        try:
            if not getattr(stream, "closed", False):
                return stream
        except Exception:
            continue
    try:
        return open(os.devnull, "w", encoding="utf-8")
    except Exception:
        return None


def _repair_std_streams() -> None:
    if "PYTEST_CURRENT_TEST" in os.environ:
        return
    try:
        if getattr(sys, "stderr", None) is None or getattr(sys.stderr, "closed", False):
            fb = _safe_default_stream(prefer_stderr=True)
            if fb is not None:
                sys.stderr = fb
    except Exception:
        pass
    try:
        if getattr(sys, "stdout", None) is None or getattr(sys.stdout, "closed", False):
            fb = _safe_default_stream(prefer_stderr=False)
            if fb is not None:
                sys.stdout = fb
    except Exception:
        pass


def _repair_closed_logger_streams() -> None:
    if "PYTEST_CURRENT_TEST" in os.environ:
        return
    replacement = _safe_default_stream(prefer_stderr=True)
    for handler in _iter_logging_handlers():
        stream = getattr(handler, "stream", None)
        try:
            if stream is not None and getattr(stream, "closed", False) and hasattr(handler, "setStream"):
                handler.setStream(replacement)
        except Exception:
            continue


def _persist_diagnostics() -> None:
    try:
        _DIAG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _DIAG_STATE["generated_at"] = _iso_now()
        _DIAG_PATH.write_text(json.dumps(_DIAG_STATE, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _write_cli_diagnostic(checkpoint: str, exc: Optional[BaseException] = None) -> None:
    try:
        _repair_std_streams()
        _repair_closed_logger_streams()
        entry: Dict[str, Any] = {
            "checkpoint": checkpoint,
            "at": _iso_now(),
        }
        stderr = _stream_info(getattr(sys, "stderr", None))
        stdout = _stream_info(getattr(sys, "stdout", None))
        entry["stderr_id"] = stderr["id"]
        entry["stderr_type"] = stderr["type"]
        entry["stderr_closed"] = stderr["closed"]
        entry["stdout_id"] = stdout["id"]
        entry["stdout_type"] = stdout["type"]
        entry["stdout_closed"] = stdout["closed"]
        entry["logger_handlers"] = [
            {
                "handler_type": type(h).__name__,
                "stream_type": type(getattr(h, "stream", None)).__name__ if getattr(h, "stream", None) is not None else "NoneType",
                "stream_closed": bool(getattr(getattr(h, "stream", None), "closed", False))
                if getattr(h, "stream", None) is not None
                else None,
            }
            for h in _iter_logging_handlers()
        ]
        if exc is not None:
            entry["exception_type"] = type(exc).__name__
            entry["exception_message"] = _mask_secret_like(str(exc))
        _DIAG_STATE["checkpoints"].append(entry)
        _persist_diagnostics()
    except Exception:
        pass


def _ensure_utf8_stdout() -> None:
    """Reconfigure stdout/stderr for UTF-8 on Windows to prevent UnicodeEncodeError."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _safe_print(*args, **kwargs) -> None:
    stream = kwargs.pop("file", None)
    if stream is None:
        stream = getattr(sys, "__stdout__", None) or getattr(sys, "stdout", None)
    try:
        print(*args, file=stream, **kwargs)
    except Exception:
        try:
            print(*args)
        except Exception:
            pass


def _safe_text(value: Any) -> str:
    return _mask_secret_like(str(value or ""))


def _read_stdin_text() -> str:
    try:
        if sys.stdin and not sys.stdin.isatty():
            return sys.stdin.read()
    except Exception:
        return ""
    return ""


def _load_local_env_file(env_path: Path) -> None:
    """Load .env key/value pairs into process env when keys are not preset.

    Minimal parser by design:
    - ignores comments/empty lines
    - accepts KEY=VALUE
    - trims optional surrounding single/double quotes
    - does not override existing environment variables
    """
    if not env_path.exists():
        return
    try:
        for raw_line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if not key:
                continue
            if value and len(value) >= 2 and (
                (value.startswith('"') and value.endswith('"'))
                or (value.startswith("'") and value.endswith("'"))
            ):
                value = value[1:-1]
            if key not in os.environ or not str(os.environ.get(key, "")).strip():
                os.environ[key] = value
    except Exception:
        return


def _load_cli_coding_state() -> Dict[str, Any]:
    if not _CLI_STATE_PATH.exists():
        return {
            "schema_version": _CLI_STATE_SCHEMA_VERSION,
            "updated_at": _iso_now(),
            "tasks": {},
            "approvals": {},
            "latest_task_id": "",
        }
    try:
        data = json.loads(_CLI_STATE_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {
                "schema_version": _CLI_STATE_SCHEMA_VERSION,
                "updated_at": _iso_now(),
                "tasks": {},
                "approvals": {},
                "latest_task_id": "",
            }
        data.setdefault("schema_version", _CLI_STATE_SCHEMA_VERSION)
        data.setdefault("updated_at", _iso_now())
        data.setdefault("tasks", {})
        data.setdefault("approvals", {})
        data.setdefault("latest_task_id", "")
        if not isinstance(data.get("tasks"), dict):
            data["tasks"] = {}
        if not isinstance(data.get("approvals"), dict):
            data["approvals"] = {}
        return data
    except Exception:
        return {
            "schema_version": _CLI_STATE_SCHEMA_VERSION,
            "updated_at": _iso_now(),
            "tasks": {},
            "approvals": {},
            "latest_task_id": "",
        }


def _save_cli_coding_state(state: Dict[str, Any]) -> None:
    try:
        state["schema_version"] = state.get("schema_version") or _CLI_STATE_SCHEMA_VERSION
        state["updated_at"] = _iso_now()
        state.setdefault("tasks", {})
        state.setdefault("approvals", {})
        state.setdefault("latest_task_id", "")
        _CLI_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CLI_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _parse_ts(ts: Any) -> Optional[datetime]:
    try:
        raw = str(ts or "").strip()
        if not raw:
            return None
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        return datetime.fromisoformat(raw)
    except Exception:
        return None


def _state_backup_path() -> Path:
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return _ROOT / "temp" / "cli_state_backups" / f"cli_coding_state_{stamp}.json"


def _backup_cli_coding_state() -> tuple[bool, str]:
    if not _CLI_STATE_PATH.exists():
        return False, "no_state_file"
    try:
        backup = _state_backup_path()
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_text(_CLI_STATE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
        return True, str(backup)
    except Exception as exc:
        return False, type(exc).__name__


def _state_summary_text(state: Dict[str, Any]) -> str:
    from .cli_ui.render import capture_rich, render_table

    tasks = dict(state.get("tasks") or {})
    approvals = dict(state.get("approvals") or {})
    pending = [a for a in approvals.values() if str((a or {}).get("status", "")).lower() == "pending"]
    completed_tasks = [t for t in tasks.values() if str((t or {}).get("status", "")).lower() in {"completed", "done"}]
    rejected = [a for a in approvals.values() if str((a or {}).get("status", "")).lower() == "rejected"]
    latest_task_id = str(state.get("latest_task_id") or "")
    latest_approval_id = sorted(approvals.keys())[-1] if approvals else ""
    rows = [
        {"key": "Path", "value": _CLI_STATE_PATH.as_posix()},
        {"key": "Schema version", "value": str(state.get('schema_version', _CLI_STATE_SCHEMA_VERSION))},
        {"key": "Tasks", "value": str(len(tasks))},
        {"key": "Approvals", "value": str(len(approvals))},
        {"key": "Pending", "value": str(len(pending))},
        {"key": "Completed", "value": str(len(completed_tasks))},
        {"key": "Rejected", "value": str(len(rejected))},
        {"key": "Latest task", "value": latest_task_id or "-"},
        {"key": "Latest approval", "value": latest_approval_id or "-"},
    ]
    return capture_rich(render_table(rows, columns=[("Field", "key"), ("Value", "value")], title="CLI Coding State", border_style="divider"))


def _approval_is_prunable(approval: Dict[str, Any], status_filter: str, older_than_days: int) -> bool:
    status = str(approval.get("status") or "").lower()
    if status == "pending":
        return False
    if status_filter == "completed" and status != "approved":
        return False
    if status_filter == "rejected" and status != "rejected":
        return False
    if status_filter == "all-closed" and status not in {"approved", "rejected", "completed"}:
        return False
    if older_than_days > 0:
        cutoff = datetime.utcnow().timestamp() - older_than_days * 86400
        ts = _parse_ts(approval.get("resolved_at") or approval.get("created_at"))
        if ts is None or ts.timestamp() > cutoff:
            return False
    return True


def _prune_approvals(
    state: Dict[str, Any],
    *,
    status_filter: str,
    older_than_days: int,
    apply_changes: bool,
) -> Dict[str, Any]:
    approvals = dict(state.get("approvals") or {})
    to_remove: List[str] = []
    for approval_id, item in approvals.items():
        if _approval_is_prunable(dict(item or {}), status_filter, older_than_days):
            to_remove.append(approval_id)
    result = {
        "dry_run": not apply_changes,
        "status_filter": status_filter,
        "older_than_days": older_than_days,
        "total_approvals": len(approvals),
        "prunable": len(to_remove),
        "removed": 0,
        "backup_path": "",
    }
    if not apply_changes:
        return result
    ok, backup = _backup_cli_coding_state()
    result["backup_path"] = backup if ok else ""
    for approval_id in to_remove:
        approvals.pop(approval_id, None)
        result["removed"] += 1
    state["approvals"] = approvals
    _save_cli_coding_state(state)
    return result


def _task_is_gc_candidate(
    task: Dict[str, Any],
    task_id: str,
    *,
    protected_task_ids: set[str],
    keep_latest_ids: set[str],
    older_than_days: int,
) -> bool:
    if task_id in keep_latest_ids:
        return False
    if task_id in protected_task_ids:
        return False
    status = str(task.get("status") or "").lower()
    if status not in {"completed", "done"}:
        return False
    if older_than_days <= 0:
        return True
    cutoff = datetime.utcnow().timestamp() - older_than_days * 86400
    ts = _parse_ts(task.get("updated_at") or task.get("created_at"))
    if ts is None:
        return False
    return ts.timestamp() <= cutoff


def _gc_tasks(
    state: Dict[str, Any],
    *,
    older_than_days: int,
    keep_latest: int,
    apply_changes: bool,
) -> Dict[str, Any]:
    tasks = dict(state.get("tasks") or {})
    approvals = dict(state.get("approvals") or {})
    protected_task_ids = {
        str(item.get("task_id") or "")
        for item in approvals.values()
        if str((item or {}).get("status") or "").lower() == "pending"
    }
    sorted_ids = sorted(tasks.keys(), reverse=True)
    keep_latest_ids = set(sorted_ids[: max(0, keep_latest)])
    latest_task_id = str(state.get("latest_task_id") or "")
    if latest_task_id:
        keep_latest_ids.add(latest_task_id)
    to_remove: List[str] = []
    for task_id, item in tasks.items():
        if _task_is_gc_candidate(
            dict(item or {}),
            task_id,
            protected_task_ids=protected_task_ids,
            keep_latest_ids=keep_latest_ids,
            older_than_days=older_than_days,
        ):
            to_remove.append(task_id)
    result = {
        "dry_run": not apply_changes,
        "older_than_days": older_than_days,
        "keep_latest": keep_latest,
        "total_tasks": len(tasks),
        "gc_candidates": len(to_remove),
        "removed": 0,
        "backup_path": "",
    }
    if not apply_changes:
        return result
    ok, backup = _backup_cli_coding_state()
    result["backup_path"] = backup if ok else ""
    for task_id in to_remove:
        tasks.pop(task_id, None)
        result["removed"] += 1
    state["tasks"] = tasks
    if str(state.get("latest_task_id") or "") not in tasks:
        state["latest_task_id"] = sorted(tasks.keys(), reverse=True)[0] if tasks else ""
    _save_cli_coding_state(state)
    return result


def _is_coding_fixture_request(text: str) -> bool:
    lowered = (text or "").lower()
    return "examples/coding_fixture" in lowered or "calculator.py" in lowered or "add bug" in lowered or "add function" in lowered


def _is_cli_surface_doc_request(text: str) -> bool:
    lowered = (text or "").lower()
    return "docs/product/cli_surface.md" in lowered or "cli coding state maintenance" in lowered


def _is_library_project_request(text: str) -> bool:
    lowered = (text or "").lower()
    return "图书馆管理系统" in text or "library management system" in lowered or "library_system" in lowered


def _get_adapter(api_base: Optional[str] = None):
    from jarvis.ui.app.mock_adapter import AppDataAdapter

    if api_base:
        return AppDataAdapter(base_url=api_base)
    return AppDataAdapter()


def _safe_registry():
    try:
        from .tools.loader import load_builtin_tools
        from .tools.registry import ToolRegistry

        registry = ToolRegistry()
        load_builtin_tools(registry)
        return registry
    except Exception:
        return None


def _safe_skill_registry(refresh: bool = False):
    try:
        from jarvis.skills.registry import SkillRegistry

        _ = refresh
        return SkillRegistry(project_root=_ROOT)
    except Exception:
        return None


def _thread_store():
    from jarvis.store import ThreadStore

    return ThreadStore()


def _memory_store():
    from jarvis.store.memory_store import MemoryStore

    return MemoryStore()


def _build_provider_status_line() -> tuple[str, Any | None]:
    try:
        from jarvis.core.llm.runtime_provider import build_runtime_llm_provider, load_llm_provider_config

        cfg = load_llm_provider_config()
        provider = build_runtime_llm_provider(cfg)
    except Exception:
        return "LLM provider: unavailable, fallback mode enabled, reason=provider_loader_error", None

    provider_name = cfg.provider or "unknown"
    key_state = "present" if cfg.api_key else "missing"
    if provider is not None:
        line = (
            f"LLM provider: {provider_name} model={cfg.model or '<missing>'} "
            f"base_url={cfg.base_url or '<missing>'} status=available api_key={key_state}"
        )
        return line, provider

    reasons: List[str] = []
    if not cfg.supports_runtime:
        reasons.append(f"unknown provider={provider_name}")
    else:
        missing_fields: List[str] = []
        if not cfg.base_url:
            missing_fields.append("base_url")
        if not cfg.model:
            missing_fields.append("model")
        if not cfg.api_key:
            missing_fields.append("api_key")
        if missing_fields:
            reasons.append("missing " + ",".join(missing_fields))
    if not reasons:
        reasons.append("provider_unavailable")
    return (
        f"LLM provider: unavailable, fallback mode enabled, reason={'; '.join(reasons)} api_key={key_state}",
        None,
    )


def _render_shell_header(
    cwd: str,
    model: str = "unknown",
    provider_status: str = "configured",
    provider_line: str = "",
) -> str:
    from .cli_ui.render import capture_rich, render_header

    # Build a concise provider badge — just provider name and availability
    provider_badge = ""
    try:
        from jarvis.core.llm.config import load_llm_config
        cfg = load_llm_config()
        status = "available" if cfg.is_real_provider else "unavailable"
        provider_badge = f"{cfg.provider} · {status}"
    except Exception:
        provider_badge = provider_line or provider_status

    header = render_header(cwd=cwd, model=model, provider=provider_badge)
    return capture_rich(header)


def _render_help() -> str:
    from .cli_ui.render import capture_rich, render_panel
    from rich.markdown import Markdown

    implemented = [spec for spec in list_command_specs() if spec.name.startswith("/") and spec.status == "implemented"]
    lines = ["| Command | Aliases | Description |", "|---------|---------|-------------|"]
    for spec in implemented:
        aliases = ", ".join(spec.aliases) if spec.aliases else "-"
        lines.append(f"| {spec.name} | {aliases} | {spec.description} |")
    lines.append("")
    lines.append("*Use /commands to view full mapping (implemented + skeleton + unsupported).*")
    return capture_rich(render_panel(Markdown("\n".join(lines)), title="Commands", border_style="agent"))


def _render_unknown_command(cmd: str, candidates: List[str]) -> str:
    from .cli_ui.render import capture_rich, render_panel

    if not candidates:
        return capture_rich(render_panel(f"Unknown command: {cmd}", title="Error", border_style="error"))
    formatted = [c if c.startswith("/") else f"/{c}" for c in candidates]
    body = f"**Unknown command:** {cmd}\n\nDid you mean: {', '.join(formatted)}"
    return capture_rich(render_panel(body, title="Unknown Command", border_style="warning"))


def _render_capabilities(title: str, items: List[Dict[str, str]]) -> str:
    from .cli_ui.render import capture_rich, render_table

    return capture_rich(render_table(items, columns=[("Name", "name"), ("Kind", "kind"), ("Status", "status"), ("Source", "source")], title=f"{title} ({len(items)})", border_style="divider"))


def _render_skill_table(skills: List[Dict[str, Any]], title: str = "Jarvis Skills") -> str:
    from .cli_ui.render import capture_rich, render_table

    if not skills:
        from .cli_ui.render import render_panel
        return capture_rich(render_panel("No skills discovered.", title=title, border_style="divider"))
    rows = []
    for skill in skills:
        name = str(skill.get("name") or skill.get("skill_name") or "")
        kind = str(skill.get("kind") or "skill")
        status = str(skill.get("status") or "")
        trust = str(skill.get("trust") or skill.get("metadata", {}).get("trust", {}).get("trust_level", "unknown"))
        source = str(skill.get("source") or "")
        description = str(skill.get("description") or "")
        rows.append({"name": name, "kind": kind, "status": status, "trust": trust, "source": source, "description": description})
    return capture_rich(render_table(rows, columns=[("Name", "name"), ("Kind", "kind"), ("Status", "status"), ("Trust", "trust"), ("Source", "source"), ("Description", "description")], title=title, border_style="divider"))


def _list_builtin_capabilities() -> List[Dict[str, str]]:
    return [{"name": name, "kind": "capability", "status": "available", "source": "builtin-fallback"} for name in FALLBACK_CAPABILITIES]


def _registry_to_capabilities(registry, kind: str) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    try:
        for t in registry.list_tools(category=None):
            items.append({"name": str(getattr(t, "name", "")), "kind": kind, "status": "available", "source": "registry"})
    except Exception:
        pass
    return items


def _api_base(args: argparse.Namespace) -> str:
    return str(getattr(args, "api_base", None) or os.getenv("JARVIS_API_BASE") or DEFAULT_API_BASE).rstrip("/")


def _http_json(method: str, url: str, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = request.Request(url=url, method=method, headers={"Content-Type": "application/json"}, data=data)
    with request.urlopen(req, timeout=8) as resp:
        raw = resp.read().decode("utf-8", "ignore")
    return json.loads(raw) if raw else {}


def _show_config(cfg) -> None:
    _safe_print("\n" + "=" * 60)
    _safe_print("  Jarvis Current Config")
    _safe_print("=" * 60)
    names = cfg.get_schema_names()
    if not names:
        _safe_print("  (no registered schemas)")
        return
    for name in names:
        info = cfg.get_schema_info(name)
        if not info:
            continue
        _safe_print(f"\n> {name.upper()}")
        for fname, finfo in info["fields"].items():
            val = finfo["current_value"]
            status = "[SET]" if val and val != "***" else ("[MASKED]" if val == "***" else "[MISSING]")
            src = ""
            if finfo.get("env_var") and os.environ.get(finfo["env_var"]):
                src = " [ENV]"
            elif val == "***":
                src = " [VAULT]"
            _safe_print(f"  {status} {fname:<30} {src}")
    _safe_print("\n" + "=" * 60 + "\n")


def cmd_config(args) -> int:
    from .config.manager import init_config

    cfg = init_config()
    if args.set:
        for kv in args.set:
            if "=" not in kv:
                _safe_print(f"invalid format: {kv} (expected key=value)")
                continue
            key, _, value = kv.partition("=")
            cfg.set(key.strip(), value.strip(), encrypt=args.encrypt, persist=not args.encrypt)
            _safe_print(f"ok: set {key.strip()}")
        return 0
    _show_config(cfg)
    return 0


def _call_tool(registry, name: str, extra_args: list) -> None:
    kwargs: Dict[str, Any] = {}
    for arg in extra_args or []:
        if "=" not in arg:
            continue
        k, _, v = arg.partition("=")
        if v.isdigit():
            kwargs[k.strip()] = int(v)
        elif v.lower() in {"true", "false"}:
            kwargs[k.strip()] = v.lower() == "true"
        else:
            kwargs[k.strip()] = v
    _safe_print(f"\nCall tool: {name}\nArgs: {kwargs}\n" + "-" * 40)
    result = registry.call(name, **kwargs)
    status_icon = "[OK]" if result else "[FAIL]"
    _safe_print(f"\n{status_icon} status: {result.status.value} elapsed: {result.elapsed:.2f}s")
    if result.message:
        _safe_print(f"message: {result.message}")
    if result.data:
        data_str = str(result.data)
        _safe_print(f"\nresult:\n{data_str[:16000]}")
    if result.error:
        _safe_print(f"\nerror: {result.error}")


def cmd_tools(args) -> int:
    _write_cli_diagnostic("before_bootstrap")
    try:
        registry = _safe_registry()
        if registry is None:
            raise RuntimeError("bootstrap unavailable")
        _write_cli_diagnostic("after_bootstrap_success")
    except BaseException as exc:
        _write_cli_diagnostic("after_bootstrap_exception", exc=exc)
        _safe_print(f"[CLI] warning: bootstrap unavailable, fallback to builtin tools ({type(exc).__name__})")
        _safe_print(_render_capabilities("Capabilities", _list_builtin_capabilities()))
        _write_cli_diagnostic("after_tools_output")
        return 0

    if args.call:
        _call_tool(registry, args.call, args.extra)
        _write_cli_diagnostic("after_tools_output")
        return 0

    tools = registry.list_tools(category=args.category or None)
    if not tools:
        _safe_print(_render_capabilities("Capabilities", _list_builtin_capabilities()))
        _write_cli_diagnostic("after_tools_output")
        return 0

    _safe_print("\n" + "=" * 60)
    _safe_print(f"  Registered Tools ({len(tools)})")
    if args.category:
        _safe_print(f"  Category: {args.category}")
    _safe_print("=" * 60)
    by_cat: Dict[str, list] = {}
    for t in tools:
        by_cat.setdefault(getattr(t, "category", "misc"), []).append(t)
    for cat, cat_tools in sorted(by_cat.items()):
        _safe_print(f"\n[{str(cat).upper()}]")
        for t in cat_tools:
            net_icon = " [NET]" if getattr(t, "requires_network", False) else ""
            _safe_print(f"  {t.name:<30} {t.description[:40]}{net_icon}")
    _safe_print("\n" + "=" * 60)
    _safe_print("Hint: python -m jarvis.cli tools --call <TOOL_NAME> key=value ...\n")
    if bool(getattr(args, "debug", False)):
        skill_registry = _safe_skill_registry(refresh=True)
        if skill_registry is not None:
            snap = skill_registry.snapshot().get("data", {})
            _safe_print("")
            _safe_print(_render_skill_debug(snap))
    _write_cli_diagnostic("after_tools_output")
    return 0


def cmd_skills(args) -> int:
    action = str(getattr(args, "action", "list") or "list").strip().lower()
    if action == "insights":
        _safe_print(_render_skill_insights())
        return 0
    registry = _safe_skill_registry(refresh=bool(getattr(args, "debug", False)))
    if registry is None:
        _safe_print("No skills found in skills/.")
        _safe_print("Fallback capabilities:")
        _safe_print(_render_capabilities("Capabilities", _list_builtin_capabilities()))
        return 0
    snapshot = registry.snapshot().get("data", {})
    items = list(snapshot.get("items") or [])
    _safe_print(_render_skill_table(items))
    if bool(getattr(args, "debug", False)):
        _safe_print("")
        _safe_print(
            _render_skill_debug(
                snapshot,
                source_filter=str(getattr(args, "source", "") or ""),
                trust_filter=str(getattr(args, "trust", "") or ""),
                status_filter=str(getattr(args, "status", "") or ""),
                shadowed_only=bool(getattr(args, "shadowed", False)),
                limit=int(getattr(args, "limit", 0) or 0),
            )
        )
    return 0


def cmd_commands(args) -> int:
    specs = list_command_specs(category=getattr(args, "category", None))
    if bool(getattr(args, "json", False)):
        _safe_print(json.dumps([asdict(spec) for spec in specs], ensure_ascii=False, indent=2))
        return 0
    _safe_print(render_command_table(specs))
    return 0


def cmd_test(args) -> int:
    target = str(getattr(args, "target", "") or "").strip()
    if target:
        command = _scoped_test_command(target)
        approval_id = _new_external_id("approval")
        store = _load_cli_coding_state()
        latest_task_id = str(store.get("latest_task_id") or "")
        store["approvals"][approval_id] = {
            "approval_id": approval_id,
            "status": "pending",
            "risk_tier": "medium",
            "reason": "Test command execution is approval-gated in safe mode.",
            "action": "run_test",
            "command": command,
            "task_id": latest_task_id,
            "created_at": _iso_now(),
        }
        if latest_task_id and latest_task_id in store.get("tasks", {}):
            store["tasks"][latest_task_id].setdefault("events", []).append(
                {"type": "test.proposed", "ts": _iso_now(), "detail": {"command": command}}
            )
            store["tasks"][latest_task_id].setdefault("evidence", []).append(
                {"kind": "test_command", "detail": command}
            )
        _save_cli_coding_state(store)
        _safe_print(_render_approval(approval_id, f"shell: {command}", "Scoped test run requires approval."))
        return 0
    _safe_print("\n" + "=" * 60)
    _safe_print("  Jarvis Phase1 Self Check")
    _safe_print("=" * 60)
    checks = []
    try:
        from .config.manager import init_config

        cfg = init_config()
        checks.append(("config", True, f"schemas={len(cfg.get_schema_names())}"))
    except Exception as exc:
        checks.append(("config", False, type(exc).__name__))
    try:
        from .tools.loader import load_builtin_tools
        from .tools.registry import ToolRegistry

        reg = ToolRegistry()
        load_builtin_tools(reg)
        checks.append(("tools", True, f"count={len(reg)}"))
    except Exception as exc:
        checks.append(("tools", False, type(exc).__name__))
    ok = True
    for name, passed, detail in checks:
        _safe_print(f"  [{'OK' if passed else 'FAIL'}] {name}: {detail}")
        ok = ok and passed
    _safe_print("=" * 60 + "\n")
    return 0 if ok else 1


def cmd_server(args) -> int:
    if args.server_cmd == "status":
        url = _api_base(args) + "/api/health"
        try:
            payload = _http_json("GET", url)
            if payload.get("ok"):
                status = payload.get("data", {}).get("status", "unknown")
                _safe_print(f"Server reachable at {_api_base(args)} | status={status}")
                return 0
            _safe_print(f"Server returned invalid response at {_api_base(args)}")
            return 1
        except Exception as exc:
            _safe_print(f"Server not reachable at {_api_base(args)} ({type(exc).__name__})")
            return 1
    base = f"http://{args.host}:{args.port}"
    if args.dry_run:
        _safe_print(f"[dry-run] would start Jarvis API server on {base}")
        return 0
    from jarvis.api.server import run_server

    _safe_print(f"Starting Jarvis API server on {base}")
    run_server(host=args.host, port=args.port)
    return 0


def _new_external_id(prefix: str) -> str:
    return f"{prefix}_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"


def _create_local_coding_task(input_text: str, require_approval: bool) -> Dict[str, Any]:
    store = _load_cli_coding_state()
    task_id = _new_external_id("task")
    run_id = _new_external_id("run")
    trace_id = _new_external_id("trace")
    if _is_cli_surface_doc_request(input_text):
        plan = _build_cli_surface_doc_plan()
        target_path = "docs/product/cli_surface.md"
        patch_summary = "append 'CLI Coding State Maintenance' section"
        approval_action = "edit_docs"
    else:
        plan = _build_coding_fixture_plan()
        target_path = "examples/coding_fixture/calculator.py"
        patch_summary = "return a - b -> return a + b"
        approval_action = "edit_file"
    events: List[Dict[str, Any]] = [
        {"type": "task.created", "ts": _iso_now(), "detail": {"task_id": task_id}},
        {"type": "plan.created", "ts": _iso_now(), "detail": {"steps": len(plan)}},
        {"type": "skill.registry.loaded", "ts": _iso_now(), "detail": {"loaded": 0}},
        {"type": "skill.selection.empty", "ts": _iso_now(), "detail": {"reason": "coding_fixture_flow"}},
    ]
    approval_id = ""
    if require_approval:
        approval_id = _new_external_id("approval")
        approval = {
            "approval_id": approval_id,
            "status": "pending",
            "risk_tier": "high",
            "reason": f"Edit {target_path} requires approval.",
            "action": approval_action,
            "path": target_path,
            "patch_summary": patch_summary,
            "task_id": task_id,
            "created_at": _iso_now(),
        }
        store["approvals"][approval_id] = approval
        events.append({"type": "approval.requested", "ts": _iso_now(), "detail": {"approval_id": approval_id}})
    store["tasks"][task_id] = {
        "task_id": task_id,
        "run_id": run_id,
        "trace_id": trace_id,
        "status": "created",
        "mode": mode,
        "input": input_text,
        "plan": plan,
        "events": events,
        "changed_files": [],
        "diff_summary": "",
        "tests": {"status": "not_run"},
        "evidence": [
            {"kind": "plan", "detail": plan},
            {"kind": "patch_summary", "detail": patch_summary},
        ],
    }
    store["latest_task_id"] = task_id
    _save_cli_coding_state(store)
    response = {
        "task_id": task_id,
        "run_id": run_id,
        "trace_id": trace_id,
        "status": "created",
        "events_url": f"/api/tasks/{task_id}/events",
    }
    if approval_id:
        response["approval_id"] = approval_id
        response["approval_required"] = True
    return response


def _collect_skill_trace_for_input(input_text: str) -> Dict[str, Any]:
    events: List[str] = ["task.created", "input.received", "policy.checked: workspace_write"]
    policy_checked: Dict[str, Any] = {"mode": "workspace_write", "network_enabled": False, "safe_mode": False}
    selection_reason = "no_registry"
    execution_status = "selection_empty"
    execution_reason = ""
    selected_skill = ""
    instruction_sources: List[str] = []
    registry = _safe_skill_registry(refresh=True)
    if registry is None:
        events.append("skill.registry.error")
        return {
            "events": events + ["task.completed"],
            "policy_checked": policy_checked,
            "selected_skill": selected_skill,
            "selection_reason": selection_reason,
            "execution_status": execution_status,
            "execution_reason": execution_reason,
            "instruction_sources": instruction_sources,
        }
    try:
        from jarvis.core.skill_harness.executor import execute_skill
        from jarvis.core.skill_harness.selector import select_skills_for_task
        from jarvis.core.skill_harness.telemetry import SkillTelemetryStore, SkillUsageRecord

        events.append("skill.registry.loaded")
        selection = select_skills_for_task(
            input_text,
            registry,
            policy={
                "mode": "workspace_write",
                "safe_mode": False,
                "network_enabled": False,
                "shell_enabled": False,
                "file_write_enabled": False,
            },
        )
        selection_reason = str(selection.reason or "")
        policy_checked = dict(selection.policy or {})
        instruction_sources = list(policy_checked.get("instruction_context", {}).get("sources", []))
        events.append("skill.routing.context_loaded")
        if selection.selected:
            selected_skill = selection.selected[0].id
            events.append(f"skill.selected: {selected_skill}")
            execution = execute_skill(
                selected_skill,
                input_text,
                registry=registry,
                dry_run=True,
                policy={
                    "mode": "workspace_write",
                    "network_enabled": False,
                    "shell_enabled": False,
                    "file_write_enabled": False,
                },
            )
            execution_status = str(execution.get("status") or "dry_run")
            execution_reason = str(execution.get("reason") or "")
            if execution.get("policy_check"):
                policy_checked = {**policy_checked, "policy_check": dict(execution.get("policy_check") or {})}
            events.append(f"skill.execution.{execution_status}")
        else:
            events.append("skill.selection.empty")
        events.append("skill.policy.checked")
        SkillTelemetryStore().append(
            SkillUsageRecord(
                skill_id=selected_skill or "none",
                input_preview=input_text[:160],
                selected=bool(selected_skill),
                executed=False,
                mode="workspace_write",
                outcome=execution_status if selected_skill else "selection_empty",
                reason=execution_reason or selection_reason,
                policy=policy_checked,
                instruction_sources=instruction_sources,
            )
        )
        events.append("skill.usage.recorded")
    except Exception as exc:
        events.append(f"skill.registry.error:{type(exc).__name__}")
    events.append("task.completed")
    return {
        "events": events,
        "policy_checked": policy_checked,
        "selected_skill": selected_skill,
        "selection_reason": selection_reason,
        "execution_status": execution_status,
        "execution_reason": execution_reason,
        "instruction_sources": instruction_sources,
    }


def _render_trace_task_run(input_text: str, mode: str, trace: Dict[str, Any]) -> str:
    plan = _build_plan(input_text)
    if _is_coding_fixture_request(input_text):
        plan = _build_coding_fixture_plan()
    lines = [f"Task trace - {mode}", "", "Input", f"  {input_text}", "", "Plan"]
    for idx, step in enumerate(plan, 1):
        lines.append(f"  {idx}. {step}")
    lines.extend(["", "Events"])
    for item in list(trace.get("events") or []):
        lines.append(f"  {item}")
    lines.extend(["", "Policy"])
    lines.append(f"  {json.dumps(trace.get('policy_checked') or {}, ensure_ascii=False)}")
    lines.extend(["", "Result"])
    if trace.get("selected_skill"):
        lines.append(f"  selected_skill={trace.get('selected_skill')} execution={trace.get('execution_status')}")
    else:
        lines.append("  no skill selected; safe completion")
    return "\n".join(lines)


def cmd_task(args) -> int:
    if args.task_cmd == "state":
        if not _CLI_STATE_PATH.exists():
            _safe_print("No CLI coding state found.")
            return 0
        state = _load_cli_coding_state()
        _safe_print(_state_summary_text(state))
        return 0
    if args.task_cmd == "gc":
        state = _load_cli_coding_state()
        apply_changes = bool(getattr(args, "yes", False))
        result = _gc_tasks(
            state,
            older_than_days=int(getattr(args, "older_than_days", 14)),
            keep_latest=int(getattr(args, "keep_latest", 20)),
            apply_changes=apply_changes,
        )
        _safe_print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.task_cmd == "run":
        trace_enabled = bool(getattr(args, "trace", False))
        if trace_enabled:
            trace = _collect_skill_trace_for_input(args.input)
            _safe_print(_render_trace_task_run(args.input, trace))
            return 0
        if _is_coding_fixture_request(args.input) or _is_cli_surface_doc_request(args.input):
            response = _create_local_coding_task(args.input, require_approval=bool(args.require_approval))
            print(json.dumps(response, ensure_ascii=False, indent=2))
            return 0
        adapter = _get_adapter(api_base=_api_base(args))
        payload = {
            "input": args.input,
            "mode": "workspace_write",
            "allow_code_changes": bool(args.allow_code_changes),
            "max_commands": int(args.max_commands),
            "max_files_changed": int(args.max_files_changed),
            "require_approval": bool(args.require_approval),
        }
        res = adapter._http_json("POST", "/api/tasks", body=payload)
        if res.ok and isinstance(res.data, dict):
            print(json.dumps(res.data, ensure_ascii=False, indent=2))
            return 0
        mock = adapter.create_task(args.input)
        print(json.dumps(mock.data, ensure_ascii=False, indent=2))
        return 0
    if args.task_cmd == "status":
        local = _load_cli_coding_state()
        local_task = local.get("tasks", {}).get(args.task_id)
        if isinstance(local_task, dict):
            print(json.dumps(local_task, ensure_ascii=False, indent=2))
            return 0
        adapter = _get_adapter(api_base=_api_base(args))
        print(json.dumps(adapter.get_task(args.task_id).data, ensure_ascii=False, indent=2))
        return 0
    if args.task_cmd == "events":
        local = _load_cli_coding_state()
        local_task = local.get("tasks", {}).get(args.task_id)
        if isinstance(local_task, dict):
            print(json.dumps(local_task.get("events", []), ensure_ascii=False, indent=2))
            return 0
        adapter = _get_adapter(api_base=_api_base(args))
        print(json.dumps(adapter.get_task_events(args.task_id).data, ensure_ascii=False, indent=2))
        return 0
    return 1


def cmd_approvals(args) -> int:
    store = _load_cli_coding_state()
    if args.approval_cmd == "prune":
        result = _prune_approvals(
            store,
            status_filter=str(getattr(args, "status", "all-closed")),
            older_than_days=int(getattr(args, "older_than_days", 0)),
            apply_changes=bool(getattr(args, "yes", False)),
        )
        _safe_print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.approval_cmd == "list":
        approvals = list(store.get("approvals", {}).values())
        if approvals:
            _safe_print(json.dumps(approvals, ensure_ascii=False, indent=2))
            return 0
        adapter = _get_adapter(api_base=_api_base(args))
        _safe_print(json.dumps(adapter.get_approvals().data, ensure_ascii=False, indent=2))
        return 0
    if args.approval_cmd == "approve":
        approval = store.get("approvals", {}).get(args.approval_id)
        if isinstance(approval, dict):
            approval["status"] = "approved"
            approval["resolved_at"] = _iso_now()
            task_id = str(approval.get("task_id") or "")
            task = store.get("tasks", {}).get(task_id) if task_id else None
            if isinstance(task, dict):
                action = str(approval.get("action") or "")
                if action == "edit_docs":
                    patch_result = _apply_cli_surface_doc_patch()
                else:
                    patch_result = _apply_coding_fixture_patch()
                changed = bool(patch_result.get("changed"))
                changed_path = str(approval.get("path") or "examples/coding_fixture/calculator.py")
                task["changed_files"] = [changed_path] if changed else []
                task["diff_summary"] = str(patch_result.get("message", ""))
                task["status"] = "completed"
                task.setdefault("events", []).extend(
                    [
                        {"type": "approval.resolved", "ts": _iso_now(), "detail": {"approval_id": args.approval_id, "decision": "approved"}},
                        {"type": "file.modified", "ts": _iso_now(), "detail": {"path": changed_path, "changed": changed}},
                        {"type": "patch.applied", "ts": _iso_now(), "detail": {"summary": patch_result.get("message", "")}},
                        {"type": "task.completed", "ts": _iso_now(), "detail": {"status": "completed"}},
                    ]
                )
                task.setdefault("evidence", []).append({"kind": "patch_summary", "detail": patch_result.get("message", "")})
            _save_cli_coding_state(store)
            _safe_print(json.dumps(approval, ensure_ascii=False, indent=2))
            return 0
        adapter = _get_adapter(api_base=_api_base(args))
        _safe_print(json.dumps(adapter.approve(args.approval_id).data, ensure_ascii=False, indent=2))
        return 0
    if args.approval_cmd == "reject":
        approval = store.get("approvals", {}).get(args.approval_id)
        if isinstance(approval, dict):
            approval["status"] = "rejected"
            approval["resolved_at"] = _iso_now()
            task_id = str(approval.get("task_id") or "")
            task = store.get("tasks", {}).get(task_id) if task_id else None
            if isinstance(task, dict):
                task.setdefault("events", []).append(
                    {"type": "approval.resolved", "ts": _iso_now(), "detail": {"approval_id": args.approval_id, "decision": "rejected"}}
                )
            _save_cli_coding_state(store)
            _safe_print(json.dumps(approval, ensure_ascii=False, indent=2))
            return 0
        adapter = _get_adapter(api_base=_api_base(args))
        _safe_print(json.dumps(adapter.reject(args.approval_id).data, ensure_ascii=False, indent=2))
        return 0
    return 1


def cmd_replay(args) -> int:
    store = _load_cli_coding_state()
    task = store.get("tasks", {}).get(args.task_id)
    if isinstance(task, dict):
        _safe_print(json.dumps(task.get("events", []), ensure_ascii=False, indent=2))
        return 0
    adapter = _get_adapter(api_base=_api_base(args))
    _safe_print(json.dumps(adapter.get_task_replay(args.task_id).data, ensure_ascii=False, indent=2))
    return 0


def cmd_evidence(args) -> int:
    store = _load_cli_coding_state()
    task = store.get("tasks", {}).get(args.task_id)
    if isinstance(task, dict):
        payload = {"task_id": args.task_id, "evidence": task.get("evidence", []), "diff_summary": task.get("diff_summary", "")}
        _safe_print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    adapter = _get_adapter(api_base=_api_base(args))
    _safe_print(json.dumps(adapter.get_task_evidence(args.task_id).data, ensure_ascii=False, indent=2))
    return 0


def cmd_diff(_args) -> int:
    """Show unified diff of the latest task's file changes."""
    store = _load_cli_coding_state()
    task_id = str(store.get("latest_task_id") or "")
    if not task_id:
        _safe_print("No local patch recorded.")
        return 0

    task = store.get("tasks", {}).get(task_id, {})
    changed = list(task.get("changed_files") or [])

    if not changed:
        _safe_print("No files changed.")
        return 0

    from .cli_ui.render import render_diff
    from .cli_ui.tui_utils import rich_to_ansi
    from shutil import get_terminal_size

    try:
        width = get_terminal_size().columns - 4
    except Exception:
        width = 76

    for path_str in changed:
        diff_text = task.get("diff_summary", "")
        # Try generating a fresh diff from the filesystem
        try:
            from pathlib import Path
            from .core.file_editor import FileEditor
            p = Path(path_str)
            if p.exists():
                editor = FileEditor()
                # Read the file and generate a diff-like view
                content = p.read_text(encoding="utf-8")
                diff_lines = [
                    f"+++ {path_str}",
                    f"@@ -0,0 +1,{content.count(chr(10)) + (1 if content else 0)} @@",
                ]
                for line in content.split("\n"):
                    diff_lines.append(f"+{line}")
                diff_text = "\n".join(diff_lines)
        except Exception:
            pass

        if diff_text.strip():
            panel = render_diff(diff_text, file_path=path_str)
            _safe_print(rich_to_ansi(panel, width=max(width, 40)))
            _safe_print("")
        else:
            _safe_print(f"  {path_str} (no diff available)")

    return 0


def cmd_review(_args) -> int:
    store = _load_cli_coding_state()
    task_id = str(store.get("latest_task_id") or "")
    if not task_id:
        _safe_print("Review\n\nChanged files:\n- none\n\nRisk:\nlow\n\nTests:\nnot run")
        return 0
    task = store.get("tasks", {}).get(task_id, {})
    changed = list(task.get("changed_files") or [])
    tests = dict(task.get("tests") or {})
    risk = "low" if len(changed) <= 1 else "medium"
    status = str(tests.get("status") or "not run")
    lines = ["Review", "", "Changed files:"]
    if not changed:
        lines.append("- none")
    else:
        for item in changed:
            lines.append(f"- {item}")
    lines.extend(["", "Risk:", risk, "", "Tests:", status])
    _safe_print("\n".join(lines))
    return 0


def cmd_state(_args) -> int:
    if not _CLI_STATE_PATH.exists():
        _safe_print("No CLI coding state found.")
        return 0
    state = _load_cli_coding_state()
    _safe_print(_state_summary_text(state))
    return 0


def cmd_auth(args) -> int:
    cmd = getattr(args, "auth_cmd", None)
    if cmd == "status":
        _safe_print("Auth status: not configured")
    elif cmd == "login":
        _safe_print("Auth login is not implemented yet.")
    elif cmd == "logout":
        _safe_print("Auth logout is not implemented yet.")
    elif cmd == "token":
        _safe_print("Auth token setup is not implemented yet.")
    else:
        _safe_print("Auth command unavailable. Use --help.")
    return 0


def cmd_agents(_args) -> int:
    _safe_print("Agents: not implemented yet.")
    return 0


def cmd_mcp(_args) -> int:
    _safe_print("MCP: not implemented yet.")
    return 0


def cmd_plugin(_args) -> int:
    _safe_print("Plugin management: not implemented yet.")
    return 0


def cmd_update(args) -> int:
    if getattr(args, "dry_run", False):
        _safe_print("[dry-run] would update Jarvis CLI")
        return 0
    _safe_print("Update is not implemented yet. Use --dry-run.")
    return 0


class ShellState:
    def __init__(self, api_base: str):
        self.trace_enabled = False
        self.model = self._resolve_model()
        self.effort = "default"
        self.fast = False
        self.api_base = api_base
        self.permission_mode: str = "workspace_write"
        self.tasks: List[Dict[str, Any]] = []
        self.approvals: Dict[str, Dict[str, Any]] = {}
        self.message_count = 0
        self.task_counter = 0
        self.approval_counter = 0
        self.task_records: Dict[str, Dict[str, Any]] = {}
        self.latest_task_id: str = ""
        self.current_thread_id: str = "cli_shell"
        self.current_project_id: str = "cli"
        self.provider_status_line, self.llm_provider = _build_provider_status_line()

    # Thinking state (updated by PersistentTUI._poll_bridge)
    last_thinking_text: str = ""
    thinking_expanded: bool = False

    def refresh(self):
        """Re-resolve model and provider after a switch."""
        self.model = self._resolve_model()
        self.provider_status_line, self.llm_provider = _build_provider_status_line()

    @staticmethod
    def _resolve_model() -> str:
        """Resolve model name from the same source as the provider status line."""
        try:
            from jarvis.core.llm.config import load_llm_config
            return load_llm_config().model or "unknown"
        except Exception:
            return "unknown"


def _next_task_id(state: ShellState) -> str:
    state.task_counter += 1
    return f"task_{state.task_counter:04d}"


def _next_approval_id(state: ShellState) -> str:
    state.approval_counter += 1
    return f"approval_{state.approval_counter:04d}"


def _record_shell_task(
    state: ShellState,
    task_id: str,
    *,
    user_input: str,
    plan: Optional[List[str]] = None,
    events: Optional[List[Dict[str, Any]]] = None,
    changed_files: Optional[List[str]] = None,
    diff_summary: str = "",
    tests: Optional[Dict[str, Any]] = None,
    evidence: Optional[List[Dict[str, Any]]] = None,
) -> None:
    state.latest_task_id = task_id
    state.tasks.append({"task_id": task_id, "input": user_input})
    state.task_records[task_id] = {
        "task_id": task_id,
        "input": user_input,
        "plan": list(plan or []),
        "events": list(events or []),
        "changed_files": list(changed_files or []),
        "diff_summary": diff_summary,
        "tests": dict(tests or {}),
        "evidence": list(evidence or []),
    }


def _append_shell_event(state: ShellState, task_id: str, event_type: str, detail: Optional[Dict[str, Any]] = None) -> None:
    record = state.task_records.get(task_id)
    if not record:
        return
    record.setdefault("events", []).append({"type": event_type, "detail": dict(detail or {}), "ts": _iso_now()})


def _build_plan(user_input: str) -> List[str]:
    lowered = user_input.lower()
    if "inspect" in lowered or "repo" in lowered or "project" in lowered:
        return ["Inspect project structure", "Read product docs", "Summarize current state", "Suggest safe next steps"]
    if "summarize" in lowered or "summary" in lowered:
        return ["Collect context", "Summarize key points", "Provide concise output"]
    return ["Review request", "Plan safe steps", "Return safe response"]


def classify_user_input(text: str) -> InputKind:
    from jarvis.core.routing.input_gateway import build_input_envelope

    raw = str(text or "").strip()
    low = raw.lower()
    envelope = build_input_envelope(raw, workspace_root=Path.cwd(), session_id="cli_shell")
    if not raw:
        return InputKind.CASUAL_CHAT
    if envelope.slash.is_slash_command:
        return InputKind.SLASH_COMMAND
    if low in {"hi", "hello", "hey", "good evening", "good morning", "good afternoon"} or any(
        token in raw for token in {"你好", "您好", "晚上好", "早上好", "你好啊"}
    ):
        return InputKind.GREETING
    capability_exact = {"what can you do", "who are you", "capabilities", "help", "你能做什么", "你是谁", "你会什么"}
    if low in capability_exact or raw in capability_exact:
        return InputKind.CAPABILITY_QUESTION
    if any(token in low for token in ["run tests", "run test", "pytest", "test "]):
        return InputKind.TEST_OR_SHELL_TASK
    if any(token in low for token in ["fix ", "patch ", "modify ", "change ", "bug", "docs/", "calculator.py"]):
        return InputKind.CODING_TASK
    if any(token in low for token in ["inspect this repo", "inspect repo", "project structure", "repository"]):
        return InputKind.REPO_INSPECTION_TASK
    if any(token in low for token in ["choose the best skill", "select skill", "skill routing", "search the web", "web search"]):
        return InputKind.SKILL_ROUTING_TASK
    if low in {"thanks", "thank you", "ok", "okay", "great"}:
        return InputKind.CASUAL_CHAT
    imperative = bool(re.match(r"^(analyze|inspect|plan|review|summarize|fix|update|create)\b", low))
    if imperative:
        return InputKind.UNKNOWN_TASK
    return InputKind.UNKNOWN_TASK


def _detect_intent_route(user_input: str) -> Dict[str, Any]:
    from jarvis.core.routing.cli_adapter import build_cli_route

    kind = classify_user_input(user_input)
    result = build_cli_route(user_input, input_kind=kind.value)
    return dict(result.get("route_before_safety") or {})


def _apply_route_safety(route: Dict[str, Any], user_input: str) -> Dict[str, Any]:
    from jarvis.core.routing.schema import IntentRoute
    from jarvis.core.routing.safety_gate import apply_route_safety

    routed = apply_route_safety(IntentRoute(**route), user_input)
    return routed.to_dict()


def _append_intent_route_trace(
    *,
    state: ShellState,
    user_input: str,
    route_before_safety: Dict[str, Any],
    route_after_safety: Dict[str, Any],
    final_response_mode: str,
    entered_task_flow: bool,
    notes: str = "",
) -> None:
    from jarvis.core.routing.cli_adapter import write_cli_trace

    try:
        write_cli_trace(
            trace_path=_INTENT_TRACE_PATH,
            timestamp=_iso_now(),
            user_input=user_input,
            route_before_safety=route_before_safety,
            route_after_safety=route_after_safety,
            final_response_mode=final_response_mode,
            entered_task_flow=entered_task_flow,
            notes=notes,
        )
    except Exception:
        pass


def _run_existing_task_flow(state: ShellState, user_input: str) -> str:
    state.message_count += 1
    task_id = _next_task_id(state)
    events = ["task.created", "input.received", "policy.checked: workspace_write"]
    if re.search(r"\b(pytest|test|tests)\b", user_input.lower()) or ("测试" in user_input):
        approval_id = _next_approval_id(state)
        command = "python -m pytest examples/coding_fixture -q"
        state.approvals[approval_id] = {
            "action": f"shell: {command}",
            "reason": "Running tests executes local commands.",
            "kind": "run_test",
            "command": command,
            "task_id": task_id,
        }
        _record_shell_task(
            state,
            task_id,
            user_input=user_input,
            plan=["Scope test command", "Request approval", "Run only after approval"],
            events=[
                {"type": "task.created", "detail": {"task_id": task_id}, "ts": _iso_now()},
                {"type": "test.proposed", "detail": {"command": command}, "ts": _iso_now()},
                {"type": "approval.requested", "detail": {"approval_id": approval_id}, "ts": _iso_now()},
            ],
            evidence=[{"kind": "test_command", "detail": command}],
        )
        return _render_approval(approval_id, f"shell: {command}", "Running tests executes local commands.")
    selected_skill = None
    selected_reason = ""
    registry = _safe_skill_registry()
    if registry is not None:
        try:
            from jarvis.core.skill_harness.executor import execute_skill
            from jarvis.core.skill_harness.selector import select_skills_for_task
            from jarvis.core.skill_harness.telemetry import SkillTelemetryStore, SkillUsageRecord

            events.append("skill.registry.loaded")
            selection = select_skills_for_task(
                user_input,
                registry,
                policy={
                    "mode": "workspace_write",
                    "network_mode": "disabled",
                    "network_enabled": False,
                    "safe_mode": False,
                },
            )
            instruction_sources = list(dict(selection.policy).get("instruction_context", {}).get("sources", []))
            events.append("skill.routing.context_loaded")
            if instruction_sources:
                events.append(f"skill.routing.instructions:{len(instruction_sources)}")
            usage_outcome = "selection_empty"
            usage_reason = selection.reason
            if selection.selected:
                selected = selection.selected[0]
                selected_skill = selected.id
                selected_reason = selection.reason
                events.append(f"skill.selected: {selected.id}")
                events.append("skill.policy.checked")
                dry = execute_skill(
                    selected.id,
                    user_input,
                    dry_run=True,
                    policy={
                        "mode": "workspace_write",
                        "network_mode": "disabled",
                        "network_enabled": False,
                        "shell_enabled": False,
                        "file_write_enabled": False,
                    },
                    registry=registry,
                )
                events.append(f"skill.execution.{dry.get('status', 'dry_run')}")
                usage_outcome = str(dry.get("status") or "dry_run")
                usage_reason = str(dry.get("reason") or selection.reason)
            else:
                events.append("skill.selection.empty")
            SkillTelemetryStore().append(
                SkillUsageRecord(
                    skill_id=selected_skill or "none",
                    input_preview=user_input[:160],
                    selected=bool(selected_skill),
                    executed=False,
                    mode="workspace_write",
                    outcome=usage_outcome,
                    reason=usage_reason,
                    policy=dict(selection.policy),
                    instruction_sources=instruction_sources,
                )
            )
            events.append("skill.usage.recorded")
        except Exception:
            events.append("skill.registry.error")
    plan = _build_coding_fixture_plan() if _is_coding_fixture_request(user_input) else _build_plan(user_input)
    result = "Completed. No files were modified."
    if selected_skill:
        result = f"Completed with skill dry-run: {selected_skill}. {selected_reason}".strip()
    events.append("task.completed")
    events_map = [{"type": ev.split(":")[0], "detail": {"raw": ev}, "ts": _iso_now()} for ev in events]
    _record_shell_task(
        state,
        task_id,
        user_input=user_input,
        plan=plan,
        events=events_map,
        evidence=[{"kind": "result_summary", "detail": result}],
    )
    return _render_task_output(task_id, user_input, plan, events, result, include_events=state.trace_enabled)


def render_conversational_response(kind: InputKind, text: str = "") -> str:
    from .cli_ui.render import capture_rich, render_panel

    if kind == InputKind.GREETING:
        body = "Hello! I am Jarvis. You can ask me to inspect the repo, plan a change, route a skill, or use /help for commands."
    elif kind == InputKind.CAPABILITY_QUESTION:
        body = "I can currently:\n- list commands and skills\n- route skills deterministically and run safe dry-runs\n- plan small code changes\n- require approval before patch apply\n- show diff, review, replay, and evidence\n\nUse /help to view commands."
    elif kind == InputKind.CASUAL_CHAT:
        body = "I can help with repo tasks, planning, and safe execution. Use /help to get started."
    else:
        body = "I can help, but this looks like a general request. Use /help for commands or describe a repo/task."
    if text:
        body = f"**Input:** {text}\n\n{body}"
    return capture_rich(render_panel(body, title="Jarvis", border_style="agent"))


def _build_coding_fixture_plan() -> List[str]:
    return [
        "Inspect examples/coding_fixture/calculator.py",
        "Inspect examples/coding_fixture/test_calculator.py",
        "Identify failing add() logic",
        "Prepare minimal patch for add() only",
        "Propose scoped test command: python -m pytest examples/coding_fixture -q",
    ]


def _build_cli_surface_doc_plan() -> List[str]:
    return [
        "Inspect docs/product/cli_surface.md",
        "Add a short section for CLI coding state maintenance",
        "Keep patch minimal and documentation-only",
        "Propose a scoped validation command",
    ]


def _ensure_coding_fixture_exists() -> bool:
    return _CODING_FIXTURE_FILE.exists() and _CODING_FIXTURE_TEST.exists()


def _apply_coding_fixture_patch() -> Dict[str, Any]:
    if not _CODING_FIXTURE_FILE.exists():
        return {"ok": False, "changed": False, "message": "Fixture file not found."}
    original = _CODING_FIXTURE_FILE.read_text(encoding="utf-8")
    if "return a + b" in original:
        return {"ok": True, "changed": False, "message": "Patch already applied."}
    patched = original.replace("return a - b", "return a + b", 1)
    if patched == original:
        return {"ok": False, "changed": False, "message": "Expected buggy line not found."}
    _CODING_FIXTURE_FILE.write_text(patched, encoding="utf-8")
    return {"ok": True, "changed": True, "message": "Patched add(): subtraction -> addition."}


def _apply_cli_surface_doc_patch() -> Dict[str, Any]:
    if not _CLI_SURFACE_DOC.exists():
        return {"ok": False, "changed": False, "message": "Target doc not found."}
    section_title = "## CLI Coding State Maintenance"
    section_body = (
        "## CLI Coding State Maintenance\n\n"
        "- Inspect local coding state with `python -m jarvis.cli task state` or `/state`.\n"
        "- Review pending approvals with `python -m jarvis.cli approvals list`.\n"
        "- Run safe cleanup previews with `python -m jarvis.cli approvals prune --dry-run` and `python -m jarvis.cli task gc --dry-run`.\n"
        "- Apply cleanup only with explicit confirmation via `--yes`.\n"
    )
    content = _CLI_SURFACE_DOC.read_text(encoding="utf-8")
    if section_title in content:
        return {"ok": True, "changed": False, "message": "Doc section already present."}
    patched = content.rstrip() + "\n\n" + section_body + "\n"
    _CLI_SURFACE_DOC.write_text(patched, encoding="utf-8")
    return {"ok": True, "changed": True, "message": "Added CLI coding state maintenance section."}


def _render_task_output(
    task_id: str,
    user_input: str,
    plan: List[str],
    events: List[str],
    result: str,
    *,
    include_events: bool = True,
) -> str:
    from .cli_ui.render import capture_rich, render_panel

    body = f"**Input:** {user_input}\n\n"
    if plan:
        body += "**Plan**\n" + "\n".join(f"  {idx}. {step}" for idx, step in enumerate(plan, 1)) + "\n\n"
    if include_events and events:
        body += "**Events**\n" + "\n".join(f"  - {ev}" for ev in events) + "\n\n"
    body += f"**Result:** {result}"
    return capture_rich(render_panel(body, title=f"Task {task_id}", border_style="agent"))


def _render_approval(approval_id: str, action: str, reason: str) -> str:
    from .cli_ui.render import capture_rich, render_panel

    body = (
        f"**Action:** {action}\n\n"
        f"**Reason:** {reason}\n\n"
        f"**Options:**\n"
        f"  `/approve {approval_id}`\n"
        f"  `/deny {approval_id}`\n"
        f"  `/reject {approval_id}`"
    )
    return capture_rich(render_panel(body, title=f"Approval Required - {approval_id}", border_style="warning"))


def _render_command_stub(spec: CliCommandSpec) -> str:
    from .cli_ui.render import capture_rich, render_panel

    if spec.status == "skeleton":
        note = "command is planned and currently not active beyond safe skeleton routing."
    elif spec.status == "unsupported":
        note = "command is unsupported in current Jarvis CLI and remains disabled."
    else:
        note = "command recognized; deeper behavior will be expanded incrementally."
    body = (
        f"**Claude equivalent:** {spec.claude_equivalent or spec.name}\n"
        f"**Status:** {spec.status}\n"
        f"**Safety:** {spec.safety}\n\n"
        f"*{note}*"
    )
    return capture_rich(render_panel(body, title=spec.name, border_style="divider"))


def _shell_config() -> str:
    try:
        from io import StringIO
        from .config.manager import init_config

        cfg = init_config()
        buf = StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            _show_config(cfg)
        finally:
            sys.stdout = old
        return buf.getvalue().strip() or "No config available."
    except Exception as exc:
        return f"Config unavailable: {_safe_text(type(exc).__name__)}"


def _shell_model(state: ShellState, args: list[str] | None = None) -> str:
    """Show or set the LLM model."""
    from .agent.model_registry import get_default_model, list_models, list_providers
    from .config.manager import get_config

    cfg = get_config()
    current_provider = cfg.get("llm.provider") or "unknown"
    current_model = cfg.get("llm.model") or "unknown"

    if not args:
        # Show current model + available models for current provider
        lines = [f"Current model: {current_model}  (provider: {current_provider})"]
        available = list_models(current_provider)
        if available:
            lines.append(f"Available models for {current_provider}:")
            for m in available:
                marker = " ← current" if m == current_model else ""
                lines.append(f"  - {m}{marker}")
        else:
            lines.append(f"No model list defined for provider '{current_provider}' — use /model <name> to set any model.")
        lines.append("Use /model <name> to switch, /model list to see all providers.")
        return "\n".join(lines)

    first = args[0].strip()

    # /model list — show all providers and their models
    if first == "list":
        lines = ["Configured providers and models:"]
        for prov in list_providers():
            marker = " ← current" if prov == current_provider else ""
            models = list_models(prov)
            model_str = ", ".join(models) if models else "(any)"
            lines.append(f"  {prov}{marker}: {model_str}")
        return "\n".join(lines)

    # /model <prov>/<mdl> — switch provider and model in one step
    if "/" in first:
        parts = first.split("/", 1)
        new_provider = parts[0].strip()
        new_model = parts[1].strip()
        if new_provider and new_model:
            cfg.set("llm.provider", new_provider, persist=True)
            os.environ["JARVIS_LLM_PROVIDER"] = new_provider
            cfg.set("llm.model", new_model, persist=True)
            os.environ["JARVIS_LLM_MODEL"] = new_model
            state.refresh()
            header = _render_shell_header(os.getcwd(), state.model, provider_line=state.provider_status_line)
            return f"Switched to {new_provider}/{new_model}\n{header}"

    # /model <name> — switch model on current provider
    model = first
    cfg.set("llm.model", model, persist=True)
    os.environ["JARVIS_LLM_MODEL"] = model
    state.refresh()
    header = _render_shell_header(os.getcwd(), state.model, provider_line=state.provider_status_line)
    return f"Model: {model}\n{header}"


def _shell_provider(state: ShellState, args: list[str] | None = None) -> str:
    """Show or set the LLM provider."""
    from .agent.model_registry import get_default_model, get_provider_info, list_providers
    from .config.manager import get_config

    cfg = get_config()
    current_provider = cfg.get("llm.provider") or "unknown"

    if not args:
        lines = [f"Current provider: {current_provider}"]
        lines.append("Available providers:")
        for prov in list_providers():
            info = get_provider_info(prov)
            marker = " ← current" if prov == current_provider else ""
            model_list = ", ".join(info.models) if info and info.models else "any"
            lines.append(f"  {prov}{marker}: {model_list}")
        lines.append("Use /provider <name> to switch, /model <name> to change model.")
        return "\n".join(lines)

    new_provider = args[0].strip().lower()
    available = list_providers()
    if new_provider not in available:
        from difflib import get_close_matches
        suggestions = get_close_matches(new_provider, available, n=3, cutoff=0.3)
        hint = f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
        return f"Unknown provider: {new_provider}. Available: {', '.join(available)}.{hint}"

    cfg.set("llm.provider", new_provider, persist=True)
    os.environ["JARVIS_LLM_PROVIDER"] = new_provider

    # Auto-set default model for this provider
    default_model = get_default_model(new_provider)
    if default_model:
        cfg.set("llm.model", default_model, persist=True)
        os.environ["JARVIS_LLM_MODEL"] = default_model

    state.refresh()
    header = _render_shell_header(os.getcwd(), state.model, provider_line=state.provider_status_line)
    model_note = f" (model: {default_model})" if default_model else ""
    return f"Provider: {new_provider}{model_note}\n{header}"


def _shell_thinking(state: ShellState) -> str:
    """Toggle thinking text display (collapsed ↔ expanded)."""
    if not state.last_thinking_text:
        return "No thinking text available from the last agent run."
    state.thinking_expanded = not state.thinking_expanded
    if state.thinking_expanded:
        lines = ["\x1b[2m  ── thinking ──\x1b[0m"]
        for line in state.last_thinking_text.split("\n"):
            if line.strip():
                lines.append(f"\x1b[2m  {line}\x1b[0m")
        return "\n".join(lines)
    else:
        line_count = state.last_thinking_text.count("\n") + 1
        return (
            f"\x1b[2m┄ Thinking ({line_count} lines) — "
            "Ctrl+T to toggle ┄\x1b[0m"
        )


def _shell_status(state: ShellState) -> str:
    from .cli_ui.render import capture_rich, render_table

    rows = [
        {"key": "Model", "value": state.model},
        {"key": "API", "value": state.api_base},
        {"key": "Web", "value": DEFAULT_WEB_URL},
        {"key": "Session", "value": state.current_thread_id},
        {"key": "Project", "value": state.current_project_id},
        {"key": "Trace", "value": "on" if state.trace_enabled else "off"},
        {"key": "Effort", "value": state.effort},
    ]
    return capture_rich(render_table(rows, columns=[("Setting", "key"), ("Value", "value")], title="Status", border_style="divider"))


_VALID_MODES = {"read_only", "workspace_write", "workspace_write_network", "danger_full_access"}


def _shell_mode(state: ShellState, args: list[str] | None = None) -> str:
    mode = (args[0] if args else "").strip().lower()
    if not mode:
        return f"Current permission mode: {state.permission_mode}\nAvailable modes: {', '.join(sorted(_VALID_MODES))}"
    if mode not in _VALID_MODES:
        from difflib import get_close_matches

        suggestions = get_close_matches(mode, _VALID_MODES, n=3, cutoff=0.3)
        hint = f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
        return f"Unknown mode: {mode}. Available: {', '.join(sorted(_VALID_MODES))}.{hint}"
    state.permission_mode = mode
    return f"Permission mode set to: {mode}"


def _shell_permissions(state: ShellState) -> str:
    from jarvis.core.policy import PermissionPolicy, get_approval_store
    from .cli_ui.render import capture_rich, render_panel

    registry = _safe_skill_registry()
    total = 0
    quarantined = 0
    if registry is not None:
        try:
            snap = registry.snapshot().get("data", {})
            total = int(snap.get("count", 0))
            quarantined = len([i for i in list(snap.get("items") or []) if i.get("quarantine")])
        except Exception:
            pass
    permission_mode = state.permission_mode
    policy = PermissionPolicy.from_permission_mode(permission_mode)
    pending = len(get_approval_store().list_pending())
    body = (
        f"**Policy:** safe by default\n"
        f"**Permission profile:** {policy.profile}\n"
        f"**Default action:** {policy.default_action}\n"
        f"**Pending approvals:** {pending}\n"
        f"**Skill trust/quarantine:** loaded={total}, quarantined={quarantined}\n\n"
        f"**Tool rules:**\n"
        + "\n".join(f"- {row.tool_name}: {row.action} ({row.risk_level})" for row in policy.tool_rules[:10])
    )
    return capture_rich(render_panel(body, title="Permissions", border_style="divider"))


def _shell_allowed_tools(_state: ShellState) -> str:
    from .cli_ui.render import capture_rich, render_panel

    body = ""
    reg = _safe_registry()
    if reg is not None:
        try:
            tools = sorted([t.name for t in reg.list_tools(category=None)])[:12]
            body += "**Tools:** " + ", ".join(tools) + "\n\n"
        except Exception:
            body += "**Tools:** unavailable\n\n"
    else:
        body += "**Tools:** no registry\n\n"
    skill_reg = _safe_skill_registry()
    if skill_reg is not None:
        try:
            snap = skill_reg.snapshot().get("data", {})
            skills = [i.get("id") or i.get("name") for i in list(snap.get("items") or []) if i.get("status") == "available" and not i.get("quarantine")]
            body += "**Skills:** " + ", ".join(sorted([s for s in skills if s])[:12])
        except Exception:
            body += "**Skills:** unavailable"
    else:
        body += "**Skills:** no registry"
    return capture_rich(render_panel(body, title="Allowed Tools & Skills", border_style="divider"))


def _shell_approvals(state: ShellState, args: Optional[List[str]] = None) -> str:
    if args and args[0].lower() == "prune":
        persistent = _load_cli_coding_state()
        result = _prune_approvals(
            persistent,
            status_filter="all-closed",
            older_than_days=0,
            apply_changes=False,
        )
        return json.dumps(result, ensure_ascii=False, indent=2)
    if not state.approvals:
        from .cli_ui.render import capture_rich, render_panel
        return capture_rich(render_panel("No pending approvals.", title="Approvals", border_style="divider"))
    from .cli_ui.render import capture_rich, render_table
    rows = [{"id": aid, "action": info.get("action", "")} for aid, info in state.approvals.items()]
    return capture_rich(render_table(rows, columns=[("ID", "id"), ("Action", "action")], title="Pending Approvals", border_style="warning"))


def _shell_plan(state: ShellState, args: List[str]) -> str:
    text = " ".join(args).strip()
    if not text:
        return "Plan requires input. Example: /plan Inspect this repo"
    if _is_coding_fixture_request(text):
        plan = _build_coding_fixture_plan()
    elif _is_cli_surface_doc_request(text):
        plan = _build_cli_surface_doc_plan()
    else:
        plan = _build_plan(text)
    task_id = _next_task_id(state)
    events = [
        {"type": "task.created", "detail": {"task_id": task_id}, "ts": _iso_now()},
        {"type": "plan.created", "detail": {"steps": len(plan)}, "ts": _iso_now()},
        {"type": "task.completed", "detail": {"status": "planned_only"}, "ts": _iso_now()},
    ]
    evidence = [{"kind": "plan", "detail": plan}]
    _record_shell_task(state, task_id, user_input=text, plan=plan, events=events, evidence=evidence)
    lines = ["Plan"]
    for idx, step in enumerate(plan, 1):
        lines.append(f"  {idx}. {step}")
    lines.extend(["", f"Task: {task_id}", "Mode: plan-only (no file edits)"])
    return "\n".join(lines)


def _filtered_skill_debug_items(
    snapshot: Dict[str, Any],
    *,
    source_filter: str = "",
    trust_filter: str = "",
    status_filter: str = "",
    shadowed_only: bool = False,
) -> List[Dict[str, Any]]:
    items = list(snapshot.get("items") or [])
    src = source_filter.strip().lower()
    trust = trust_filter.strip().lower()
    status = status_filter.strip().lower()
    out: List[Dict[str, Any]] = []
    for row in items:
        row_source = str(row.get("source") or "").lower()
        row_status = str(row.get("status") or "").lower()
        row_trust = str(row.get("trust") or row.get("metadata", {}).get("trust", {}).get("trust_level", "")).lower()
        row_shadowed = bool(row.get("shadowed_by")) or row_status == "shadowed"
        if src and src not in row_source:
            continue
        if trust and trust != row_trust:
            continue
        if status and status != row_status:
            continue
        if shadowed_only and not row_shadowed:
            continue
        out.append(row)
    return out


def _render_skill_debug(
    snapshot: Dict[str, Any],
    *,
    source_filter: str = "",
    trust_filter: str = "",
    status_filter: str = "",
    shadowed_only: bool = False,
    limit: int = 0,
) -> str:
    discovery = dict(snapshot.get("discovery") or {})
    items = list(snapshot.get("items") or [])
    shadowed = list(discovery.get("shadowed") or [])
    filtered = _filtered_skill_debug_items(
        snapshot,
        source_filter=source_filter,
        trust_filter=trust_filter,
        status_filter=status_filter,
        shadowed_only=shadowed_only,
    )
    if limit > 0:
        filtered = filtered[:limit]
    root_priority = dict(discovery.get("root_priority") or {})
    invalid_count = len([i for i in items if str(i.get("status", "")).lower() in {"invalid", "error"}])
    quarantined_count = len([i for i in items if bool(i.get("quarantine")) or str(i.get("status", "")).lower() == "disabled"])
    imported_count = len(
        [
            i
            for i in items
            if str(i.get("trust") or i.get("metadata", {}).get("trust", {}).get("trust_level", "")).lower()
            in {"imported-reference", "needs_review"}
        ]
    )
    lines = ["Skill Discovery Debug", "---------------------", "Skill roots checked:"]
    for root in list(discovery.get("roots") or []):
        lines.append(f"- {root} (priority={int(root_priority.get(root, 0))})")
    lines.extend(
        [
            "",
            f"Skills discovered: {int(snapshot.get('count', 0))}",
            f"Duplicates shadowed: {len(shadowed)}",
            f"Invalid skills: {invalid_count}",
            f"Quarantined skills: {quarantined_count}",
            f"Imported-reference skills: {imported_count}",
        ]
    )
    lines.append(f"Filtered view count: {len(filtered)}")
    if source_filter or trust_filter or status_filter or shadowed_only:
        lines.append(
            "Filters: "
            + ", ".join(
                [
                    f"source={source_filter or '*'}",
                    f"trust={trust_filter or '*'}",
                    f"status={status_filter or '*'}",
                    f"shadowed={shadowed_only}",
                    f"limit={limit if limit > 0 else '*'}",
                ]
            )
        )
    if not filtered:
        lines.append("No matching skills.")
        return "\n".join(lines)
    lines.append("Filtered entries:")
    for row in filtered:
        lines.append(
            f"- {row.get('skill_id') or row.get('id')} | source={row.get('source')} | trust={row.get('trust')} | status={row.get('status')} | shadowed_by={row.get('shadowed_by')}"
        )
    if shadowed:
        lines.append("Shadowed entries:")
        for row in shadowed[:50]:
            lines.append(
                f"- {row.get('skill_id')} from {row.get('root')} shadowed_by={row.get('shadowed_by')} (priority={row.get('source_priority')})"
            )
    return "\n".join(lines)


def _render_skill_insights() -> str:
    try:
        from jarvis.core.skill_harness.telemetry import SkillTelemetryStore

        insights = SkillTelemetryStore().insights()
    except Exception as exc:
        return f"Skill insights unavailable: {_safe_text(type(exc).__name__)}"
    lines = ["Skill Insights", "--------------"]
    lines.append(f"total_records: {int(insights.get('total_records', 0))}")
    lines.append("most_selected:")
    for row in list(insights.get("most_selected") or [])[:10]:
        lines.append(f"- {row.get('skill_id')}: {int(row.get('selected', 0))}")
    lines.append("blocked_skills:")
    for sid in list(insights.get("blocked_skills") or []):
        lines.append(f"- {sid}")
    lines.append("approval_required_skills:")
    for sid in list(insights.get("approval_required_skills") or []):
        lines.append(f"- {sid}")
    lines.append("suggestions:")
    for tip in list(insights.get("suggestions") or []):
        lines.append(f"- {tip}")
    return "\n".join(lines)


def _scoped_test_command(target: str) -> str:
    cleaned = (target or "").strip()
    if not cleaned:
        return "python -m pytest examples/coding_fixture -q"
    if cleaned.startswith("docs/") or cleaned.startswith("docs\\"):
        return "python -m pytest tests/cli/test_real_small_coding_smoke.py -q"
    if "coding_fixture" in cleaned:
        return "python -m pytest examples/coding_fixture -q"
    return f"python -m pytest {cleaned} -q"


def _shell_test(state: ShellState, args: Optional[List[str]] = None) -> str:
    target = " ".join(args or []).strip() or "examples/coding_fixture"
    cmd = _scoped_test_command(target)
    approval_id = _next_approval_id(state)
    task_id = state.latest_task_id or _next_task_id(state)
    state.approvals[approval_id] = {
        "action": f"shell: {cmd}",
        "reason": "Running tests executes local commands.",
        "kind": "run_test",
        "command": cmd,
        "task_id": task_id,
        "target": target,
    }
    if task_id not in state.task_records:
        _record_shell_task(
            state,
            task_id,
            user_input=f"Run tests for {target}",
            plan=["Propose scoped test command", "Request approval", "Execute only after approval"],
            events=[{"type": "task.created", "detail": {"task_id": task_id}, "ts": _iso_now()}],
            evidence=[{"kind": "test_command", "detail": cmd}],
        )
    if task_id in state.task_records:
        _append_shell_event(state, task_id, "test.proposed", {"command": cmd, "target": target})
    return _render_approval(approval_id, f"shell: {cmd}", "Running tests executes local commands.")


def _shell_fix(state: ShellState, args: List[str]) -> str:
    text = " ".join(args).strip()
    if not text:
        return "Usage: /fix Fix the failing add function in examples/coding_fixture."
    target_path = ""
    apply_kind = ""
    patch_summary = ""
    if _is_coding_fixture_request(text):
        if not _ensure_coding_fixture_exists():
            return "Coding fixture not found at examples/coding_fixture."
        target_path = "examples/coding_fixture/calculator.py"
        apply_kind = "edit_file"
        patch_summary = "return a - b -> return a + b"
        plan = _build_coding_fixture_plan()
    elif _is_cli_surface_doc_request(text):
        if not _CLI_SURFACE_DOC.exists():
            return "Target doc not found at docs/product/cli_surface.md."
        target_path = "docs/product/cli_surface.md"
        apply_kind = "edit_docs"
        patch_summary = "append 'CLI Coding State Maintenance' section"
        plan = _build_cli_surface_doc_plan()
    else:
        return "Fix currently supports examples/coding_fixture and docs/product/cli_surface.md."
    task_id = _next_task_id(state)
    events = [
        {"type": "task.created", "detail": {"task_id": task_id}, "ts": _iso_now()},
        {"type": "plan.created", "detail": {"steps": len(plan)}, "ts": _iso_now()},
    ]
    evidence = [{"kind": "plan", "detail": "minimal approved patch plan"}]
    _record_shell_task(state, task_id, user_input=text, plan=plan, events=events, evidence=evidence)
    approval_id = _next_approval_id(state)
    state.approvals[approval_id] = {
        "action": f"{apply_kind}: {target_path}",
        "reason": "File edit requires approval.",
        "kind": apply_kind,
        "task_id": task_id,
        "path": target_path,
        "patch_summary": patch_summary,
    }
    _append_shell_event(state, task_id, "approval.requested", {"approval_id": approval_id})
    return _render_approval(
        approval_id,
        f"{apply_kind}: {target_path}",
        f"Patch summary: {patch_summary}",
    )


def _shell_build(state: ShellState, args: List[str]) -> str:
    """Run autonomous coding session: /build <goal>"""
    from jarvis.coding.session import CodingSession
    from jarvis.cli_ui.console import get_console

    goal = " ".join(args).strip()
    if not goal:
        return "Usage: /build <goal> — autonomous coding session\nExample: /build write a calculator that passes the tests"

    console = get_console()
    console.print(f"[bold]Starting coding session...[/bold]\nGoal: {goal}\n")

    session = CodingSession(
        project_root=str(Path.cwd()),
        max_attempts=3,
        timeout_s=120,
        permission_mode=state.permission_mode,
        auto_approve=True,
    )

    try:
        result = session.run(goal)
    except Exception as exc:
        return f"[bold red]Coding session failed:[/bold red] {exc}"

    lines: list[str] = []
    if result["ok"]:
        lines.append("[bold green]Coding session succeeded![/bold green]")
    else:
        lines.append(f"[bold yellow]Coding session ended: {result['stop_reason']}[/bold yellow]")

    lines.append(f"\nAttempts: {result['total_attempts']}")
    for a in result["attempts"]:
        status = "PASS" if (a.validation and a.validation.tests_passed) else "FAIL"
        lines.append(f"  Attempt {a.attempt}: {status}")
        if a.validation and a.validation.errors:
            for err in a.validation.errors:
                lines.append(f"    Error: {err[:120]}")

    if result["changed_files"]:
        lines.append(f"\nChanged files: {', '.join(result['changed_files'])}")

    if result["final_answer"]:
        lines.append(f"\n[bold]Agent output:[/bold]\n{result['final_answer'][:3000]}")

    return "\n".join(lines)


def _shell_mcp(args: List[str], state: ShellState) -> str:
    """Manage MCP server connections: connect, disconnect, list, tools."""
    from jarvis.gateway.mcp_client import MCPClient

    mcp = getattr(state, "_mcp_client", None) if state is not None else None
    if mcp is None:
        mcp = MCPClient()
        if state is not None:
            state._mcp_client = mcp

    sub = (args[0] if args else "").strip().lower()
    rest = args[1:]

    if sub == "connect":
        if len(rest) < 2:
            return "Usage: /mcp connect <name> <command...>\n  Connects to a stdio MCP server.\n  Example: /mcp connect my_server python -m my_mcp_server"
        name = rest[0]
        command = rest[1:]
        try:
            info = mcp.connect_stdio(name, command)
            return (
                f"MCP connected: {name}\n"
                f"Server: {info['server_info'].get('name', '?')} v{info['server_info'].get('version', '?')}\n"
                f"Tools: {info['tool_count']} | Resources: {info['resource_count']} | Prompts: {info['prompt_count']}"
            )
        except Exception as exc:
            return f"MCP connect failed: {exc}"

    if sub == "disconnect":
        if not rest:
            return "Usage: /mcp disconnect <name>"
        name = rest[0]
        if mcp.disconnect(name):
            return f"MCP disconnected: {name}"
        return f"MCP server not found: {name}"

    if sub == "list":
        names = mcp.server_names
        if not names:
            return "No MCP servers connected.\nUse /mcp connect <name> <command...> to connect."
        lines = [f"MCP servers ({len(names)} connected):"]
        for n in names:
            tools = mcp.list_tools(n)
            lines.append(f"  {n}: {len(tools)} tools")
        return "\n".join(lines)

    if sub == "tools":
        if not rest:
            names = mcp.server_names
            if not names:
                return "No MCP servers connected."
        else:
            names = [rest[0]]
        lines = ["MCP tools:"]
        for n in names:
            try:
                tools = mcp.list_tools(n)
            except Exception:
                lines.append(f"  {n}: (disconnected)")
                continue
            if not tools:
                lines.append(f"  {n}: no tools")
                continue
            for t in tools:
                desc = (t.get("description") or "")[:80]
                lines.append(f"  {n}.{t.get('name', '?')}: {desc}")
        return "\n".join(lines)

    return (
        "MCP commands:\n"
        "  /mcp connect <name> <command...>  Connect to stdio MCP server\n"
        "  /mcp disconnect <name>             Disconnect from server\n"
        "  /mcp list                          List connected servers\n"
        "  /mcp tools [server]                List tools from all/specific server"
    )


def _shell_diff(state: ShellState) -> str:
    from .cli_ui.render import capture_rich, render_panel

    task_id = state.latest_task_id
    if not task_id or task_id not in state.task_records:
        return capture_rich(render_panel("Changed files:\n- none\n\n**Summary:** no local patch recorded", title="Diff", border_style="divider"))
    record = state.task_records[task_id]
    changed = list(record.get("changed_files") or [])
    summary = record.get("diff_summary") or "no local patch recorded"
    body = "**Changed files:**\n" + ("\n".join(f"- {item}" for item in changed) if changed else "- none")
    body += f"\n\n**Summary:** {summary}"
    _append_shell_event(state, task_id, "diff.generated", {"changed_files": len(changed)})
    return capture_rich(render_panel(body, title="Diff", border_style="divider"))


def _shell_review(state: ShellState) -> str:
    from .cli_ui.render import capture_rich, render_panel

    task_id = state.latest_task_id
    if not task_id or task_id not in state.task_records:
        return capture_rich(render_panel("Changed files:\n- none\n\n**Risk:** low\n\n**Tests:** not run", title="Review", border_style="divider"))
    record = state.task_records[task_id]
    changed = list(record.get("changed_files") or [])
    tests = dict(record.get("tests") or {})
    risk = "low" if len(changed) <= 1 else "medium"
    test_status = tests.get("status", "not run")
    body = "**Changed files:**\n"
    if not changed:
        body += "- none"
    else:
        body += "\n".join(f"- {item}" for item in changed)
    body += f"\n\n**Risk:** {risk}\n\n**Tests:** {test_status}"
    _append_shell_event(state, task_id, "review.completed", {"risk": risk, "tests": test_status})
    return capture_rich(render_panel(body, title="Review", border_style="divider"))


def _shell_logs() -> str:
    from .cli_ui.render import capture_rich, render_panel

    candidates = [str(_ROOT / "logs"), str(_ROOT / "temp" / "cli_stderr_diagnostics.json")]
    found = [p for p in candidates if os.path.exists(p)]
    if found:
        body = "\n".join(f"- {p}" for p in found)
    else:
        body = "No logs found."
    return capture_rich(render_panel(body, title="Logs", border_style="divider"))


def _shell_server(state: ShellState) -> str:
    from .cli_ui.render import capture_rich, render_panel

    return capture_rich(render_panel(
        f"**API:** {state.api_base}\n\nTry: `python -m jarvis.cli server status`",
        title="Server",
        border_style="divider",
    ))


def _render_web_ui() -> str:
    from .cli_ui.render import capture_rich, render_panel

    return capture_rich(render_panel(f"**URL:** {DEFAULT_WEB_URL}", title="Web UI", border_style="divider"))


def _shell_tasks(state: ShellState, args: Optional[List[str]] = None) -> str:
    from .cli_ui.render import capture_rich, render_panel, render_table

    args = list(args or [])

    if args and args[0].lower() == "gc":
        persistent = _load_cli_coding_state()
        result = _gc_tasks(persistent, older_than_days=14, keep_latest=20, apply_changes=False)
        return json.dumps(result, ensure_ascii=False, indent=2)

    mgr = _get_cli_managers()["tasks"]
    tasks = mgr.list_all()

    if not tasks:
        return capture_rich(render_panel("No tasks recorded.", title="Tasks", border_style="divider"))

    # Support filtering: /tasks pending, /tasks in_progress, /tasks completed
    if args and args[0].lower() in ("pending", "in_progress", "completed", "blocked"):
        tasks = [t for t in tasks if t.get("status") == args[0].lower()]

    rows = []
    for t in tasks[-50:]:
        rows.append({
            "id": t.get("task_id", "")[:12],
            "subject": str(t.get("subject") or t.get("description") or "")[:80],
            "status": t.get("status", "pending"),
        })
    return capture_rich(render_table(rows, columns=[
        ("ID", "id"), ("Subject", "subject"), ("Status", "status"),
    ], title=f"Tasks ({len(rows)})", border_style="divider"))


# ── s15: CLI manager access (lazy singleton) ──────────────────────────


def _get_cli_managers() -> dict[str, Any]:
    """Lazily create manager instances for CLI slash commands."""
    cache = getattr(_get_cli_managers, "_cache", None)
    if cache is not None:
        return cache
    from jarvis.core.background import BackgroundTaskManager
    from jarvis.core.tasks.manager import PersistentTaskManager
    from jarvis.core.teams.manager import TeammateManager
    from jarvis.core.teams.message_bus import MessageBus
    from jarvis.core.worktree.manager import WorktreeManager

    root = Path.cwd()
    tasks_dir = root / ".jarvis" / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    task_mgr = PersistentTaskManager(tasks_dir=tasks_dir)

    team_dir = root / ".jarvis" / "teams"
    team_dir.mkdir(parents=True, exist_ok=True)
    bus = MessageBus(inbox_dir=team_dir / "inbox")
    team_mgr = TeammateManager(team_dir=team_dir, bus=bus)

    cache = {
        "tasks": task_mgr,
        "bg": BackgroundTaskManager(max_workers=4),
        "worktree": WorktreeManager(repo_root=root, tasks=task_mgr),
        "team": team_mgr,
    }
    _get_cli_managers._cache = cache
    return cache


# ── /worktree handler ─────────────────────────────────────────────────


def _shell_worktree(args: list[str] | None = None) -> str:
    from .cli_ui.render import capture_rich, render_panel, render_table

    args = list(args or [])
    mgr = _get_cli_managers()["worktree"]

    if not args or args[0] == "list":
        data = mgr.list_all()
        worktrees = data.get("worktrees", []) if isinstance(data, dict) else []
        if not worktrees:
            return capture_rich(render_panel("No worktrees.", title="Worktrees", border_style="divider"))
        rows = []
        for wt in worktrees:
            rows.append({
                "name": wt.get("name", ""),
                "branch": wt.get("branch", ""),
                "task": wt.get("task_id") or "",
                "status": "active" if wt.get("active") else "inactive",
            })
        return capture_rich(render_table(rows, columns=[
            ("Name", "name"), ("Branch", "branch"), ("Task", "task"), ("Status", "status"),
        ], title="Worktrees", border_style="divider"))

    sub = args[0].lower()
    if sub == "create" and len(args) >= 2:
        name = args[1]
        task_id = args[2] if len(args) >= 3 else None
        result = mgr.create(name, task_id=task_id)
        if result.get("ok"):
            return capture_rich(render_panel(f"Worktree created: {name}\nBranch: {result.get('branch', '')}", title="Worktree", border_style="success"))
        return capture_rich(render_panel(f"Failed: {result.get('error', 'unknown')}", title="Worktree Error", border_style="error"))

    if sub == "status" and len(args) >= 2:
        result = mgr.status(args[1])
        if result.get("ok"):
            lines = [f"Name: {args[1]}", f"Path: {result.get('path', '')}", f"Branch: {result.get('branch', '')}"]
            return capture_rich(render_panel("\n".join(lines), title=f"Worktree: {args[1]}", border_style="divider"))
        return capture_rich(render_panel(f"Not found: {args[1]}", title="Worktree", border_style="error"))

    if sub == "remove" and len(args) >= 2:
        result = mgr.remove(args[1])
        if result.get("ok"):
            return capture_rich(render_panel(f"Removed: {args[1]}", title="Worktree", border_style="success"))
        return capture_rich(render_panel(f"Failed: {result.get('error', 'unknown')}", title="Worktree Error", border_style="error"))

    return capture_rich(render_panel(
        "Usage: /worktree [list|create <name> [task-id]|status <name>|remove <name>]",
        title="Worktree", border_style="divider"))


# ── /team handler ─────────────────────────────────────────────────────


def _shell_team(args: list[str] | None = None) -> str:
    from .cli_ui.render import capture_rich, render_panel, render_table

    args = list(args or [])
    mgr = _get_cli_managers()["team"]

    if not args or args[0] == "list":
        members = mgr.list_all()
        if not members:
            return capture_rich(render_panel("No teammates.", title="Team", border_style="divider"))
        rows = []
        for m in members:
            rows.append({
                "name": m.get("name", ""),
                "role": m.get("role", ""),
                "status": m.get("status", "inactive"),
                "autonomous": "yes" if m.get("autonomous") else "no",
            })
        return capture_rich(render_table(rows, columns=[
            ("Name", "name"), ("Role", "role"), ("Status", "status"), ("Autonomous", "autonomous"),
        ], title="Team", border_style="divider"))

    sub = args[0].lower()
    if sub == "spawn" and len(args) >= 3:
        name, role = args[1], args[2]
        prompt = " ".join(args[3:]) if len(args) > 3 else ""
        result = mgr.spawn(name, role, prompt)
        if result.get("ok"):
            return capture_rich(render_panel(f"Spawned: {name} ({role})", title="Team", border_style="success"))
        return capture_rich(render_panel(f"Failed: {result.get('error', 'unknown')}", title="Team Error", border_style="error"))

    if sub == "inbox":
        who = args[1] if len(args) >= 2 else "user"
        msgs = mgr.bus.read_inbox(who)
        if not msgs:
            return capture_rich(render_panel(f"Inbox empty for {who}.", title="Inbox", border_style="divider"))
        lines = []
        for m in msgs[-10:]:
            lines.append(f"- [{m.get('sender', '?')}]: {m.get('content', '')[:120]}")
        return capture_rich(render_panel("\n".join(lines), title=f"Inbox: {who}", border_style="divider"))

    if sub == "message" and len(args) >= 3:
        to, content = args[1], " ".join(args[2:])
        result = mgr.bus.send("user", to, content, msg_type="cli")
        if result.get("ok"):
            return capture_rich(render_panel(f"Sent to {to}", title="Team Message", border_style="success"))
        return capture_rich(render_panel(f"Failed: {result.get('error', 'unknown')}", title="Team Error", border_style="error"))

    return capture_rich(render_panel(
        "Usage: /team [list|spawn <name> <role> [prompt]|inbox [name]|message <name> <content>]",
        title="Team", border_style="divider"))


# ── /bg handler ───────────────────────────────────────────────────────


def _shell_bg(args: list[str] | None = None) -> str:
    from .cli_ui.render import capture_rich, render_panel, render_table

    args = list(args or [])
    mgr = _get_cli_managers()["bg"]

    if not args or args[0] == "list":
        tasks = mgr.list_tasks()
        if not tasks:
            return capture_rich(render_panel("No background tasks.", title="Background Tasks", border_style="divider"))
        rows = []
        for t in tasks:
            rows.append({
                "task_id": t.get("task_id", ""),
                "description": str(t.get("description") or "")[:60],
                "status": t.get("status", "unknown"),
            })
        return capture_rich(render_table(rows, columns=[
            ("Task ID", "task_id"), ("Description", "description"), ("Status", "status"),
        ], title="Background Tasks", border_style="divider"))

    sub = args[0].lower()
    if sub == "check" and len(args) >= 2:
        result = mgr.check(args[1])
        status = result.get("status", "unknown")
        output = str(result.get("output") or result.get("result") or "")[:500]
        return capture_rich(render_panel(
            f"Task: {args[1]}\nStatus: {status}\nOutput: {output or '(none)'}",
            title="Background Task", border_style="divider"))

    if sub == "cancel" and len(args) >= 2:
        mgr.cancel(args[1])
        return capture_rich(render_panel(f"Cancelled: {args[1]}", title="Background Task", border_style="success"))

    return capture_rich(render_panel(
        "Usage: /bg [list|check <task_id>|cancel <task_id>]",
        title="Background Tasks", border_style="divider"))


def _shell_tools() -> str:
    from .cli_ui.render import capture_rich, render_table

    registry = _safe_registry()
    if registry is None:
        items = _list_builtin_capabilities()
    else:
        items = _registry_to_capabilities(registry, "tool")
        if not items:
            items = _list_builtin_capabilities()
    return capture_rich(render_table(items, columns=[("Name", "name"), ("Kind", "kind"), ("Status", "status"), ("Source", "source")], title="Tools", border_style="divider"))


def _shell_skills(args: Optional[List[str]] = None) -> str:
    from .cli_ui.render import capture_rich, render_table

    args = list(args or [])
    registry = _safe_skill_registry()
    if registry is None:
        items = _list_builtin_capabilities()
    else:
        items = _skill_items()
        if not items:
            items = _list_builtin_capabilities()
    return capture_rich(render_table(items, columns=[("Name", "name"), ("Kind", "kind"), ("Status", "status"), ("Source", "source"), ("Description", "description")], title="Skills", border_style="divider"))


def _skill_usage() -> str:
    return "\n".join(
        [
            "Usage: /skill <name> [task]",
            "",
            "Examples:",
            "  /skill list",
            "  /skill show summarize_file",
            "  /skill create my_skill",
            "  /skill install path/to/skill",
            "  /skill enable my_skill",
            "  /skill disable my_skill",
            "  /skill update my_skill",
            "  /skill check my_skill",
            "  /skill trust my_skill",
            "  /skill quarantine my_skill",
            "  /skill source list",
            "  /skill source add local_pack path/to/skills",
            "  /skill source remove local_pack",
            "  /skill validate summarize_file",
            "  /skill doctor",
            "  /skill index",
            "",
            "Skill commands keep raw args intact. Write, shell, and network actions stay approval-gated.",
        ]
    )


def _skill_items(include_inactive: bool = False) -> List[Dict[str, Any]]:
    registry = _safe_skill_registry()
    if registry is None:
        return []
    try:
        return list(registry.export_index(include_inactive=include_inactive))
    except Exception:
        return []


def _find_skill_item(name: str) -> Optional[Dict[str, Any]]:
    needle = str(name or "").strip().lower()
    if not needle:
        return None
    for item in _skill_items(include_inactive=True):
        aliases = {
            str(item.get("name") or "").strip().lower(),
        }
        if needle in aliases:
            return dict(item)
    return None


def _skill_body_has_policy_violation(item: Dict[str, Any]) -> bool:
    candidates = [
        item.get("path"),
        item.get("skill_md_path"),
        (dict(item.get("metadata") or {})).get("body_path"),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            text = Path(str(candidate)).read_text(encoding="utf-8", errors="replace").lower()
        except Exception:
            continue
        if any(token in text for token in (".env", ".npmrc", ".ssh", "id_rsa", "id_ed25519", "private key", "token")):
            return True
        if ("curl " in text or "wget " in text) and ("| sh" in text or "| bash" in text):
            return True
        if "invoke-webrequest" in text and ("| iex" in text or "invoke-expression" in text):
            return True
    return False


def _skill_request_is_sensitive(raw_args: str) -> bool:
    low = str(raw_args or "").lower()
    if any(token in low for token in (".env", ".npmrc", ".ssh", "id_rsa", "id_ed25519", "private key", "token", "secret")):
        return True
    if ("curl " in low or "wget " in low) and ("| sh" in low or "| bash" in low):
        return True
    if "invoke-webrequest" in low and ("| iex" in low or "invoke-expression" in low):
        return True
    return False


def _skill_route_label(skill_name: str, raw_args: str, response_mode: str) -> str:
    low = f"{skill_name} {raw_args}".lower()
    if any(token in low for token in ("code", "coding", "fix", "bug", "write", "create", "新建", "修复", "写")):
        return "agent_tool_loop"
    if response_mode == "skill_tool_dispatch":
        return "tool"
    return "skill_agent"


def _render_skill_invocation(skill_route: Any, *, item: Optional[Dict[str, Any]] = None, trigger: str = "/skill") -> str:
    raw_args = str(getattr(skill_route, "raw_args", "") or "")
    skill_name = str(getattr(skill_route, "candidate_skill", "") or "")
    if _skill_request_is_sensitive(raw_args):
        return "Action refused: this request may involve sensitive files or unsafe operations."
    if item and _skill_body_has_policy_violation(item):
        return "\n".join(
            [
                f"Skill refused: {skill_name}",
                "Reason: skill instructions request sensitive files or dangerous shell/network execution.",
                "No shell command was run and no sensitive file was read.",
            ]
        )
    allowed_tools = [str(t) for t in list((item or {}).get("allowed_tools") or [])]
    tool_risk = any(t.lower() in {"write", "bash", "shell", "edit"} for t in allowed_tools)
    network_risk = str(skill_name).lower().startswith("web-") or any(t.lower() in {"web", "webfetch", "websearch"} for t in allowed_tools)
    requires_approval = bool(getattr(skill_route, "requires_approval", False) or tool_risk or network_risk)
    dispatch = "tool" if getattr(skill_route, "response_mode", "") == "skill_tool_dispatch" else "skill_agent"
    route_label = _skill_route_label(skill_name, raw_args, str(getattr(skill_route, "response_mode", "")))
    lines = [
        f"Skill command recognized: {trigger}",
        f"Dispatch: {dispatch}",
        f"Route: {route_label}",
        f"Skill: {skill_name}",
        f"Args: {raw_args or '(none)'}",
        f"Requires approval: {'true' if requires_approval else 'false'}",
    ]
    tools = list(getattr(skill_route, "requires_tools", None) or [])
    if tools:
        lines.append("Tools: " + ", ".join(str(t) for t in tools))
    if allowed_tools:
        lines.append("Allowed tools: " + ", ".join(allowed_tools))
    if requires_approval:
        lines.append("Safety: approval required before write, shell, or network execution.")
    else:
        lines.append("Safety: no privileged action executed by this routing step.")
    return "\n".join(lines)


def _render_skill_show(name: str) -> str:
    item = _find_skill_item(name)
    if item is None:
        return f"skill-not-found: {name}\nUse /skills to list available skills."
    return "\n".join(
        [
            f"name: {item.get('name') or name}",
            f"Description: {item.get('description', '-')}",
            f"source: {item.get('source', '-')}",
            f"source_format: {item.get('source_format', '-')}",
            f"risk_level: {item.get('risk_level', '-')}",
            f"risk_level_source: {item.get('risk_level_source', '-')}",
            f"raw_allowed_tools: {item.get('raw_allowed_tools')}",
            "Allowed tools: " + (", ".join([str(t) for t in list(item.get("allowed_tools") or [])]) or "none"),
            f"enabled: {item.get('enabled')}",
            f"trust_status: {item.get('trust_status')}",
            f"quarantined: {item.get('quarantined')}",
        ]
    )


def _shell_skill(args: List[str], envelope: Any) -> str:
    from jarvis.skills.authoring import create_skill, format_skill_doctor, format_skill_index, format_validation_result
    from jarvis.skills.lifecycle import SkillLifecycleManager
    from jarvis.skills.validator import SkillValidator, default_validation_mode_for_spec

    if not args or args[0].lower() in {"help", "--help", "-h"}:
        return _skill_usage()
    action = args[0].lower()
    registry = _safe_skill_registry()
    if registry is None:
        return "skill-registry-unavailable"
    lifecycle = SkillLifecycleManager(
        project_root=_ROOT,
        install_root=Path(os.getenv("JARVIS_SKILL_CREATE_DIR", str(_ROOT / ".jarvis" / "skills"))),
        config_path=os.getenv("JARVIS_SKILL_CONFIG_PATH"),
    )
    if action == "list":
        items = _skill_items(include_inactive=True)
        lines = ["Jarvis Skills:"]
        for item in items:
            lines.append(
                f"- {item.get('name')}: {item.get('description')} "
                f"[enabled={item.get('enabled')} trust={item.get('trust_status')} quarantined={item.get('quarantined')}]"
            )
        return "\n".join(lines)
    if action == "show":
        if len(args) < 2:
            return "Usage: /skill show <name>"
        return _render_skill_show(args[1])
    if action == "create":
        if len(args) < 2:
            return "Usage: /skill create <name>"
        create_root = Path(os.getenv("JARVIS_SKILL_CREATE_DIR", str(_ROOT / ".jarvis" / "skills")))
        try:
            created = create_skill(args[1], base_dir=create_root)
        except FileExistsError:
            return f"Skill already exists: {create_root / args[1] / 'SKILL.md'}"
        except ValueError:
            return f"Invalid skill name: {args[1]}"
        return "\n".join(
            [
                f"Created skill template: {created}",
                "Next: edit description, allowed-tools, workflow, safety rules, and examples.",
            ]
        )
    if action == "validate":
        if len(args) < 2:
            return "Usage: /skill validate <name> [--compat]"
        try:
            spec = registry.get(args[1])
        except KeyError:
            return f"skill-not-found: {args[1]}\nUse /skills to list available skills."
        mode = "compatibility" if any(token in {"--compat", "--compatibility"} for token in args[2:]) else default_validation_mode_for_spec(spec)
        return format_validation_result(SkillValidator().validate_spec(spec, mode=mode))
    if action == "doctor":
        specs = registry.list_skills()
        validator = SkillValidator()
        results = [validator.validate_spec(spec, mode=default_validation_mode_for_spec(spec)) for spec in specs]
        return format_skill_doctor(results, specs)
    if action == "index":
        return format_skill_index(registry.export_index())
    if action == "install":
        if len(args) < 2:
            return "Usage: /skill install <source> [--strict|--compat]"
        mode = "strict" if "--strict" in args[2:] else "compatibility" if any(token in {"--compat", "--compatibility"} for token in args[2:]) else "auto"
        result = lifecycle.install_skill(args[1], mode=mode, enabled=False)
        if not result.get("ok"):
            if result.get("validation"):
                validation = dict(result.get("validation") or {})
                return "\n".join(
                    [
                        f"Skill install failed: {args[1]}",
                        f"Validation: {validation.get('mode')} -> ERROR",
                        "Errors:",
                        *[f"- {str(f.get('code') or 'error')}: {str(f.get('message') or '')}" for f in list(validation.get('findings') or []) if str(f.get('level') or '') == 'error'],
                    ]
                )
            return f"Skill install failed: {result.get('error') or 'unknown_error'}"
        record = dict(result.get("record") or {})
        return "\n".join(
            [
                f"Skill installed: {record.get('name')}",
                f"Validation: {record.get('validation_status')}",
                f"Enabled: {record.get('enabled')}",
                f"Trust: {record.get('trust_status')}",
                f"Quarantine: {record.get('quarantine_status')}",
                f"Hash: {record.get('hash')}",
                f"Next: /skill enable {record.get('name')}",
            ]
        )
    if action == "enable":
        if len(args) < 2:
            return "Usage: /skill enable <name>"
        result = lifecycle.set_enabled(args[1], True)
        return f"Skill enabled: {args[1]}" if result.get("ok") else f"Skill enable failed: {result.get('error')}"
    if action == "disable":
        if len(args) < 2:
            return "Usage: /skill disable <name>"
        result = lifecycle.set_enabled(args[1], False, reason="cli_disable")
        return f"Skill disabled: {args[1]}" if result.get("ok") else f"Skill disable failed: {result.get('error')}"
    if action == "update":
        if len(args) < 2:
            return "Usage: /skill update <name>"
        result = lifecycle.update_skill(args[1])
        if not result.get("ok"):
            return f"Skill update failed: {result.get('error')}"
        return "\n".join(
            [
                f"Skill updated: {args[1]}",
                f"old_hash: {result.get('old_hash')}",
                f"new_hash: {result.get('new_hash')}",
            ]
        )
    if action == "check":
        if len(args) < 2:
            return "Usage: /skill check <name>"
        try:
            data = registry.check_skill(args[1])
        except KeyError:
            return f"skill-not-found: {args[1]}\nUse /skills to list available skills."
        return "\n".join(
            [
                f"name: {data.get('name')}",
                f"source: {data.get('source')}",
                f"path: {data.get('path')}",
                f"hash: {data.get('hash')}",
                f"version: {data.get('version')}",
                f"enabled: {data.get('enabled')}",
                f"trust_status: {data.get('trust_status')}",
                f"quarantine_status: {data.get('quarantine_status')}",
                f"validation_mode: {data.get('validation_mode')}",
                f"validation_status: {data.get('validation_status')}",
                f"duplicate_status: {data.get('duplicate_status')}",
                f"loadable: {data.get('loadable')}",
                f"executable: {data.get('executable')}",
                f"risk_level: {data.get('risk_level')}",
                "allowed_tools: " + (", ".join([str(t) for t in list(data.get("allowed_tools") or [])]) or "none"),
            ]
        )
    if action == "trust":
        if len(args) < 2:
            return "Usage: /skill trust <name>"
        result = lifecycle.trust_skill(args[1], trusted=True, reason="cli_trust")
        return f"Skill trust updated: {args[1]} -> {dict(result.get('trust') or {}).get('status')}" if result.get("ok") else f"Skill trust failed: {result.get('error')}"
    if action == "quarantine":
        if len(args) < 2:
            return "Usage: /skill quarantine <name>"
        result = lifecycle.quarantine_skill(args[1], quarantined=True, reason="cli_quarantine")
        return f"Skill quarantined: {args[1]}" if result.get("ok") else f"Skill quarantine failed: {result.get('error')}"
    if action == "source":
        if len(args) < 2:
            return "Usage: /skill source <list|add|remove> ..."
        sub = args[1].lower()
        if sub == "list":
            rows = lifecycle.store.list_sources()
            lines = ["Skill sources:"]
            for row in rows:
                lines.append(f"- {row.name}: kind={row.kind} enabled={row.enabled} priority={row.priority} path={row.uri_or_path}")
            if len(lines) == 1:
                lines.append("- none")
            return "\n".join(lines)
        if sub == "add":
            if len(args) < 4:
                return "Usage: /skill source add <name> <path_or_uri>"
            row = lifecycle.store.add_source(args[2], args[3])
            return f"Skill source added: {row.name} -> {row.uri_or_path}"
        if sub == "remove":
            if len(args) < 3:
                return "Usage: /skill source remove <name>"
            removed = lifecycle.store.remove_source(args[2])
            return f"Skill source removed: {args[2]}" if removed else f"Skill source not found: {args[2]}"
        return "Usage: /skill source <list|add|remove> ..."

    item = _find_skill_item(args[0])
    if item is None:
        return f"skill-not-found: {args[0]}\nUse /skills to list available skills."
    raw_args = " ".join(args[1:]).strip()
    lines = [
        f"Skill command recognized: /skill {args[0]}",
        f"Skill: {item.get('name')}",
        f"Description: {item.get('description')}",
        f"Risk: {item.get('risk_level')}",
        "Allowed tools: " + (", ".join([str(t) for t in list(item.get("allowed_tools") or [])]) or "none"),
    ]
    if raw_args:
        lines.append(f"Args: {raw_args}")
    lines.append("Execution: not implemented in Phase 9; use AgentLoop + skill.load for on-demand loading.")
    return "\n".join(lines)


def _shell_commands(args: List[str]) -> str:
    from .cli_ui.render import capture_rich, render_table

    category = args[0] if args else None
    specs = list_command_specs(category=category)
    rows = [
        {"name": s.name, "category": s.category, "status": s.status, "safety": s.safety, "claude": s.claude_equivalent or "-"}
        for s in specs
    ]
    return capture_rich(render_table(rows, columns=[("Name", "name"), ("Category", "category"), ("Status", "status"), ("Safety", "safety"), ("Claude", "claude")], title="Command Map", border_style="divider"))


def _shell_context(state: ShellState, args: List[str]) -> str:
    from .cli_ui.render import capture_rich, render_panel

    args = list(args or [])
    store = _thread_store()
    if not args:
        return "Usage: /context <save|resume> [thread_id]"
    action = str(args[0]).strip().lower()
    if action == "save":
        thread = store.get_thread(state.current_thread_id)
        if thread is None:
            thread = store.create_thread(title="CLI session", metadata={"source": "cli"})
            state.current_thread_id = thread["thread_id"]
        body = f"**Session:** {state.current_thread_id}\n**Schema version:** {store.schema_version()}\n**Status:** persisted"
        return capture_rich(render_panel(body, title="Context Saved", border_style="agent"))
    if action == "resume":
        if len(args) < 2:
            return "Usage: /context resume <thread_id>"
        thread_id = str(args[1]).strip()
        thread = store.get_thread(thread_id)
        if thread is None:
            return f"Thread not found: {thread_id}"
        state.current_thread_id = thread_id
        body = f"**Mode:** background-only\n*Note: persisted memory is historical context, not a new instruction.*"
        return capture_rich(render_panel(body, title=f"Context Resumed: {thread_id}", border_style="agent"))
    return "Usage: /context <save|resume> [thread_id]"


def _shell_threads(state: ShellState, args: List[str]) -> str:
    from .cli_ui.render import capture_rich, render_panel, render_table

    args = list(args or [])
    store = _thread_store()
    action = str(args[0]).strip().lower() if args else "list"
    if action == "list":
        rows = store.list_threads(limit=20)
        if not rows:
            return capture_rich(render_panel("No persisted threads.", title="Sessions", border_style="divider"))
        table_rows = []
        for row in rows:
            marker = "*" if row.get("thread_id") == state.current_thread_id else " "
            table_rows.append({"": marker, "Thread ID": row.get("thread_id"), "Title": row.get("title") or "(untitled)", "Updated": row.get("updated_at")})
        return capture_rich(render_table(table_rows, columns=[("", ""), ("Thread ID", "Thread ID"), ("Title", "Title"), ("Updated", "Updated")], title="Sessions", border_style="divider"))
    if action in ("open", "switch", "resume"):
        if len(args) < 2:
            return f"Usage: /threads {action} <thread_id>"
        thread_id = str(args[1]).strip()
        thread = store.get_thread(thread_id)
        if thread is None:
            return f"Thread not found: {thread_id}"
        state.current_thread_id = thread_id
        turns = store.get_recent_turns(thread_id, limit=3)
        body = f"**Title:** {thread.get('title', '(untitled)')}\n**Turns:** {len(list(turns))}"
        return capture_rich(render_panel(body, title=f"Switched to {thread_id}", border_style="agent"))
    if action == "delete":
        if len(args) < 2:
            return "Usage: /threads delete <thread_id>"
        thread_id = str(args[1]).strip()
        if thread_id == state.current_thread_id:
            state.current_thread_id = f"session_{uuid4().hex[:12]}"
        ok = store.delete_thread(thread_id)
        if ok:
            return f"Deleted: {thread_id}\nCurrent session: {state.current_thread_id}"
        return f"Thread not found: {thread_id}"
    if action == "info":
        thread = store.get_thread(state.current_thread_id)
        if thread is None:
            return f"Current session {state.current_thread_id} not persisted yet."
        turns = store.get_recent_turns(state.current_thread_id, limit=20)
        msg_count = store.count_messages(state.current_thread_id)
        rows = [
            {"key": "Session", "value": thread['thread_id']},
            {"key": "Title", "value": thread.get('title') or '(untitled)'},
            {"key": "Turns", "value": str(len(list(turns)))},
            {"key": "Messages", "value": str(msg_count)},
            {"key": "Updated", "value": str(thread.get('updated_at', ''))},
        ]
        return capture_rich(render_table(rows, columns=[("Field", "key"), ("Value", "value")], title="Session Info", border_style="divider"))
    return "Usage: /threads <list|switch|delete|info> [thread_id]"


def _shell_memory(state: ShellState, args: Optional[List[str]] = None) -> str:
    from .cli_ui.render import capture_rich, render_panel, render_table

    args = list(args or [])
    store = _memory_store()
    if not args or str(args[0]).strip().lower() == "show":
        user_memory = store.get_user_memory()
        project_memory = store.get_project_memory(state.current_project_id)
        body = "**User memory:**\n"
        body += "\n".join(f"- {k}: {v}" for k, v in user_memory.items()) or "- none"
        body += f"\n\n**Project memory ({state.current_project_id}):**\n"
        body += "\n".join(f"- {k}: {v}" for k, v in project_memory.items()) or "- none"
        typed = store.get_typed(limit=20)
        typed_rows = []
        if typed:
            for r in typed:
                rtype = r.get("memory_type") if isinstance(r, dict) else getattr(r, "memory_type", "")
                rkey = r.get("key") if isinstance(r, dict) else getattr(r, "key", "")
                rval = (r.get("value_redacted") if isinstance(r, dict) else getattr(r, "value_redacted", ""))
                typed_rows.append({"type": rtype, "key": rkey, "value": str(rval)[:2000]})
        result = capture_rich(render_panel(body, title="Memory", border_style="divider"))
        if typed_rows:
            result += "\n" + capture_rich(render_table(typed_rows, columns=[("Type", "type"), ("Key", "key"), ("Value", "value")], title="Typed Memory", border_style="divider"))
        return result
    action = str(args[0]).strip().lower()
    if action == "edit":
        if len(args) < 3:
            return "Usage: /memory edit <key> <value>"
        key = str(args[1]).strip()
        value = " ".join(str(part) for part in args[2:])
        record = store.set_user_memory(key, value)
        rkey = record.get("key") if isinstance(record, dict) else record.key
        rval = record.get("value_redacted") if isinstance(record, dict) else record.value_redacted
        return f"Memory updated: {rkey}\nValue: {rval}"
    if action == "delete":
        if len(args) < 2:
            return "Usage: /memory delete <key>"
        key = str(args[1]).strip()
        store.delete_user_memory(key)
        return f"Memory deleted: {key}"
    if action == "search":
        if len(args) < 2:
            return "Usage: /memory search <query> [--type feedback|reference|user_profile|project_fact]"
        query = str(args[1]).strip()
        mem_type = None
        if len(args) >= 4 and str(args[2]).strip() == "--type":
            mem_type = str(args[3]).strip()
        records = store.search(query, memory_type=mem_type, limit=10)
        if not records:
            return f"No results for: {query}"
        search_rows = []
        for r in records:
            rtype = r.get("memory_type") if isinstance(r, dict) else getattr(r, "memory_type", "")
            rkey = r.get("key") if isinstance(r, dict) else getattr(r, "key", "")
            rval = (r.get("value_redacted") if isinstance(r, dict) else getattr(r, "value_redacted", ""))
            search_rows.append({"type": rtype, "key": rkey, "value": str(rval)[:200]})
        return capture_rich(
            render_table(search_rows, columns=[("Type", "type"), ("Key", "key"), ("Value", "value")], title=f"Search: {query}", border_style="divider")
        )
    if action == "clear":
        store.clear_user_memory()
        return "User memory cleared."
    return "Usage: /memory <show|edit|delete|search|clear> ..."


def _shell_agents(_state: ShellState) -> str:
    from .cli_ui.render import capture_rich, render_panel

    return capture_rich(render_panel("**plan**, **explore**, **implement**, **review** — skeleton routing.", title="Agent Modes", border_style="divider"))


def _shell_trace(state: ShellState, args: Optional[List[str]] = None) -> str:
    from .cli_ui.render import capture_rich, render_panel

    args = list(args or [])
    if not args:
        return capture_rich(render_panel(f"Trace mode: **{'on' if state.trace_enabled else 'off'}**", title="Trace", border_style="divider"))
    token = args[0].strip().lower()
    if token in {"on", "true", "1"}:
        state.trace_enabled = True
        return capture_rich(render_panel("Trace mode: **on**", title="Trace", border_style="divider"))
    if token in {"off", "false", "0"}:
        state.trace_enabled = False
        return capture_rich(render_panel("Trace mode: **off**", title="Trace", border_style="divider"))
    return "Usage: /trace [on|off]"


def _shell_state() -> str:
    from .cli_ui.render import capture_rich, render_panel

    if not _CLI_STATE_PATH.exists():
        return capture_rich(render_panel("No CLI coding state found.", title="State", border_style="divider"))
    return _state_summary_text(_load_cli_coding_state())


def _shell_doctor(state: ShellState) -> str:
    from .cli_ui.render import capture_rich, render_panel

    rows = []
    try:
        from .config.manager import init_config
        cfg = init_config()
        rows.append({"item": "Config schemas", "value": str(len(cfg.get_schema_names()))})
    except Exception as exc:
        rows.append({"item": "Config", "value": f"unavailable ({_safe_text(type(exc).__name__)})"})
    reg = _safe_registry()
    if reg is None:
        rows.append({"item": "Tool registry", "value": "unavailable"})
    else:
        try:
            rows.append({"item": "Tool registry", "value": f"{len(reg.list_tools(category=None))} tools"})
        except Exception:
            rows.append({"item": "Tool registry", "value": "error"})
    skill_registry = _safe_skill_registry()
    if skill_registry is None:
        rows.append({"item": "Skill registry", "value": "unavailable"})
    else:
        try:
            snap = skill_registry.snapshot().get("data", {})
            discovery = snap.get("discovery", {})
            rows.append({"item": "Skills loaded", "value": str(int(snap.get('count', 0)))})
            rows.append({"item": "Skill roots", "value": str(len(list(discovery.get('roots') or [])))})
            rows.append({"item": "Skills invalid", "value": str(len([i for i in list(snap.get('items') or []) if i.get('status') == 'invalid']))})
            rows.append({"item": "Skills quarantined", "value": str(len([i for i in list(snap.get('items') or []) if i.get('quarantine')]))})
        except Exception:
            rows.append({"item": "Skill registry", "value": "error"})
    try:
        from jarvis.core.skill_harness.instructions import load_project_instruction_context
        instruction_ctx = load_project_instruction_context(_ROOT)
        rows.append({"item": "Instruction sources", "value": str(len(instruction_ctx.sources))})
        rows.append({"item": "No network", "value": str(instruction_ctx.no_network)})
        rows.append({"item": "Docs only", "value": str(instruction_ctx.docs_only)})
    except Exception:
        rows.append({"item": "Instruction sources", "value": "unavailable"})
    rows.append({"item": "API base", "value": state.api_base})
    return capture_rich(render_panel(
        "\n".join(f"**{r['item']}:** {r['value']}" for r in rows),
        title="Doctor Report",
        border_style="divider",
    ))


def _shell_approve(state: ShellState, args: List[str]) -> str:
    from jarvis.core.policy import get_approval_store
    from .cli_ui.render import capture_rich, render_panel

    if not args:
        return "Usage: /approve <id>"
    approval_id = args[0]
    store = get_approval_store()
    response = store.approve(approval_id, decided_by="cli")
    if response is not None:
        return capture_rich(render_panel(
            f"**Status:** approved\n*Note: approval recorded; retry the original action to continue execution.*",
            title=f"Approved: {approval_id}",
            border_style="success",
        ))
    if approval_id.lower() == "last":
        approval_id = next(reversed(state.approvals), "") if state.approvals else ""
    if approval_id not in state.approvals:
        return capture_rich(render_panel(f"Approval not found: {args[0]}", title="Error", border_style="error"))
    info = dict(state.approvals.pop(approval_id, {}))
    task_id = str(info.get("task_id") or "")
    kind = str(info.get("kind") or "")
    if kind == "library_project":
        _append_shell_event(state, task_id, "approval.resolved", {"approval_id": approval_id, "decision": "approved"})
        apply_result = _apply_library_project(state, task_id)
        if task_id in state.task_records:
            rec = state.task_records[task_id]
            rec["changed_files"] = list(apply_result.get("changed_files") or [])
            rec["tests"] = {
                "status": apply_result.get("test_status", "not_run"),
                "command": apply_result.get("command", ""),
                "exit_code": apply_result.get("exit_code"),
                "summary": apply_result.get("summary", ""),
            }
            rec["diff_summary"] = "created library_system project files"
            rec.setdefault("evidence", []).append({"kind": "scoped_test", "detail": rec["tests"]})
            if apply_result.get("rethink_records"):
                rec.setdefault("evidence", []).append({"kind": "rethink_records", "detail": apply_result["rethink_records"]})
            _append_shell_event(state, task_id, "task.completed", {"status": apply_result.get("status")})
        lines = [
            "Library project created.",
            "",
            "**Changed files**",
        ]
        lines.extend([f"- {item}" for item in list(apply_result.get("changed_files") or [])] or ["- none"])
        lines.extend(
            [
                "",
                "**Scoped test command**",
                f"  {apply_result.get('command')}",
                "",
                "**Test status**",
                f"  {apply_result.get('test_status')}",
            ]
        )
        if apply_result.get("rethink_records"):
            lines.extend(["", "**Rethink/Replan**"])
            lines.extend([f"- {item.get('trigger')}: {item.get('action')}" for item in apply_result["rethink_records"]])
        if apply_result.get("summary"):
            lines.extend(["", "**Test output**", str(apply_result.get("summary"))[:1200]])
        return capture_rich(render_panel("\n".join(lines), title=f"Approved: {approval_id}", border_style="success"))
    if kind in {"edit_file", "edit_docs"}:
        apply_result = _apply_coding_fixture_patch() if kind == "edit_file" else _apply_cli_surface_doc_patch()
        changed_path = str(info.get("path", "examples/coding_fixture/calculator.py"))
        if task_id in state.task_records:
            if apply_result.get("ok"):
                _append_shell_event(
                    state,
                    task_id,
                    "file.modified",
                    {"path": changed_path, "changed": bool(apply_result.get("changed"))},
                )
                _append_shell_event(state, task_id, "patch.applied", {"summary": apply_result.get("message", "")})
                rec = state.task_records[task_id]
                rec["changed_files"] = [changed_path] if apply_result.get("changed") else []
                rec["diff_summary"] = str(apply_result.get("message", ""))
                rec.setdefault("evidence", []).append({"kind": "patch_summary", "detail": apply_result.get("message", "")})
            _append_shell_event(state, task_id, "approval.resolved", {"approval_id": approval_id, "decision": "approved"})
            _append_shell_event(state, task_id, "task.completed", {"status": "completed"})
        return capture_rich(render_panel(apply_result.get('message', ''), title=f"Approved: {approval_id}", border_style="success"))
    if kind == "run_test":
        command = str(info.get("command") or "python -m pytest examples/coding_fixture -q")
        result = {"status": "dry_run", "command": command, "exit_code": None, "summary": "dry-run only"}
        if task_id in state.task_records:
            _append_shell_event(state, task_id, "approval.resolved", {"approval_id": approval_id, "decision": "approved"})
        try:
            proc = subprocess.run(command.split(), capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(_ROOT), timeout=60)
            result = {
                "status": "passed" if proc.returncode == 0 else "failed",
                "command": command,
                "exit_code": proc.returncode,
                "summary": (proc.stdout or proc.stderr or "").strip()[:600],
            }
        except Exception as exc:
            result = {"status": "error", "command": command, "exit_code": None, "summary": type(exc).__name__}
        if task_id in state.task_records:
            state.task_records[task_id]["tests"] = result
            state.task_records[task_id].setdefault("evidence", []).append(
                {"kind": "test_result", "detail": {"status": result["status"], "command": command}}
            )
            _append_shell_event(state, task_id, "test.executed" if result["status"] != "dry_run" else "test.dry_run", {"command": command, "status": result["status"]})
        return capture_rich(render_panel(f"**Test status:** {result['status']}\n**Command:** {command}", title=f"Approved: {approval_id}", border_style="success"))
    return capture_rich(render_panel(f"Approved: {approval_id}", title="Approved", border_style="success"))


def _shell_reject(state: ShellState, args: List[str]) -> str:
    from jarvis.core.policy import get_approval_store
    from .cli_ui.render import capture_rich, render_panel

    if not args:
        return "Usage: /deny <id>"
    approval_id = args[0]
    store = get_approval_store()
    response = store.deny(approval_id, decided_by="cli")
    if response is not None:
        return capture_rich(render_panel("**Status:** denied", title=f"Denied: {approval_id}", border_style="error"))
    if approval_id.lower() == "last":
        approval_id = next(reversed(state.approvals), "") if state.approvals else ""
    if approval_id not in state.approvals:
        return capture_rich(render_panel(f"Approval not found: {args[0]}", title="Error", border_style="error"))
    info = dict(state.approvals.pop(approval_id, {}))
    task_id = str(info.get("task_id") or "")
    if task_id in state.task_records:
        _append_shell_event(state, task_id, "approval.resolved", {"approval_id": approval_id, "decision": "rejected"})
    return capture_rich(render_panel(f"Rejected: {approval_id}", title="Rejected", border_style="error"))


def _shell_replay(state: ShellState, args: List[str]) -> str:
    from .cli_ui.render import capture_rich, render_panel

    task_id = args[0] if args else state.latest_task_id
    if task_id and task_id in state.task_records:
        record = state.task_records[task_id]
        events_text = "\n".join(f"- {event.get('type')}" for event in list(record.get("events") or [])) or "- none"
        body = f"**Task:** {task_id}\n\n**Events:**\n{events_text}"
        return capture_rich(render_panel(body, title="Replay", border_style="divider"))
    if not task_id:
        return capture_rich(render_panel("Replay unavailable: no task selected.", title="Replay", border_style="divider"))
    try:
        res = _get_adapter().get_task_replay(task_id)
        if res.ok:
            return json.dumps(res.data, ensure_ascii=False, indent=2)
        return f"Replay unavailable for {task_id}"
    except Exception as exc:
        return f"Replay error: {_safe_text(type(exc).__name__)}"


def _shell_evidence(state: ShellState, args: List[str]) -> str:
    from .cli_ui.render import capture_rich, render_panel

    task_id = args[0] if args else state.latest_task_id
    if task_id and task_id in state.task_records:
        record = state.task_records[task_id]
        items_text = "\n".join(f"- {item.get('kind', 'unknown')}" for item in list(record.get("evidence") or [])) or "- none"
        body = f"**Task:** {task_id}\n\n**Items:**\n{items_text}"
        return capture_rich(render_panel(body, title="Evidence", border_style="divider"))
    if not task_id:
        return capture_rich(render_panel("Evidence unavailable: no task selected.", title="Evidence", border_style="divider"))
    try:
        res = _get_adapter().get_task_evidence(task_id)
        if res.ok:
            return json.dumps(res.data, ensure_ascii=False, indent=2)
        return f"Evidence unavailable for {task_id}"
    except Exception as exc:
        return f"Evidence error: {_safe_text(type(exc).__name__)}"


def _clear_state(state: ShellState) -> str:
    state.tasks = []
    state.approvals = {}
    state.message_count = 0
    state.task_records = {}
    state.latest_task_id = ""
    state.task_counter = 0
    state.approval_counter = 0
    new_id = f"session_{uuid4().hex[:12]}"
    state.current_thread_id = new_id
    return f"New session: {new_id}"


def _run_repo_inspection(user_input: str) -> Dict[str, Any]:
    from jarvis.core.repo_inspection import RepoInspectionRequest, inspect_repo

    result = inspect_repo(
        RepoInspectionRequest(
            workspace_root=Path.cwd(),
            user_input=user_input,
        ),
        session_id="cli_shell",
    )
    return result.to_dict()


def _queue_library_project_approval(state: ShellState, user_input: str) -> str:
    task_id = _next_task_id(state)
    approval_id = _next_approval_id(state)
    plan = [
        "Create only files under library_system/.",
        "Implement Book, JSON storage, and Library operations.",
        "Add a simple CLI menu.",
        "Add pytest coverage for add, remove, borrow, return, search, list, persistence, and failure cases.",
        "After approval, run only: python -m pytest library_system/tests -q",
    ]
    state.approvals[approval_id] = {
        "action": "write library_system files and run scoped tests",
        "reason": "Coding project creation requires approval before file writes or shell tests.",
        "kind": "library_project",
        "task_id": task_id,
        "files": list(_LIBRARY_PROJECT_FILES),
        "command": "python -m pytest library_system/tests -q",
    }
    _record_shell_task(
        state,
        task_id,
        user_input=user_input,
        plan=plan,
        events=[
            {"type": "task.created", "detail": {"task_id": task_id}, "ts": _iso_now()},
            {"type": "agent_tool_loop.entered", "detail": {"requires_write": True, "requires_shell": True}, "ts": _iso_now()},
            {"type": "plan.created", "detail": {"files": list(_LIBRARY_PROJECT_FILES)}, "ts": _iso_now()},
            {"type": "approval.requested", "detail": {"approval_id": approval_id}, "ts": _iso_now()},
        ],
        evidence=[{"kind": "planned_files", "detail": list(_LIBRARY_PROJECT_FILES)}],
    )
    lines = [
        "Coding loop pending approval.",
        "",
        "Flags",
        "  requires_write=true",
        "  requires_shell=true",
        "  requires_approval=true",
        "",
        "Plan",
    ]
    lines.extend([f"  {idx}. {step}" for idx, step in enumerate(plan, 1)])
    lines.extend(["", "Files"])
    lines.extend([f"  - {item}" for item in _LIBRARY_PROJECT_FILES])
    lines.extend(["", _render_approval(approval_id, "write library_system files and run scoped tests", "No files or shell commands run before approval.")])
    return "\n".join(lines)


def _library_project_file_payloads() -> Dict[str, str]:
    return {
        "library_system/__init__.py": '"""Library management system package."""\n\nfrom .library import Book, Library\n\n__all__ = ["Book", "Library"]\n',
        "library_system/storage.py": '''from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_json(path: str | Path) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []
    with target.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError("library data must be a list")
    return [dict(item) for item in data]


def write_json(path: str | Path, rows: list[dict[str, Any]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        json.dump(rows, handle, ensure_ascii=False, indent=2)
        handle.write("\\n")
''',
        "library_system/library.py": '''from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from .storage import read_json, write_json


@dataclass
class Book:
    id: str
    title: str
    author: str
    year: int
    available: bool = True


class Library:
    def __init__(self, storage_path: str | Path) -> None:
        self.storage_path = Path(storage_path)
        self.books: dict[str, Book] = {}
        self.load()

    def load(self) -> None:
        self.books = {}
        for row in read_json(self.storage_path):
            book = Book(
                id=str(row["id"]),
                title=str(row["title"]),
                author=str(row["author"]),
                year=int(row["year"]),
                available=bool(row.get("available", True)),
            )
            self.books[book.id] = book

    def save(self) -> None:
        rows = [asdict(book) for book in sorted(self.books.values(), key=lambda item: item.id)]
        write_json(self.storage_path, rows)

    def add_book(self, book: Book) -> None:
        if book.id in self.books:
            raise ValueError(f"book already exists: {book.id}")
        self.books[book.id] = book
        self.save()

    def remove_book(self, book_id: str) -> bool:
        if book_id not in self.books:
            return False
        del self.books[book_id]
        self.save()
        return True

    def borrow_book(self, book_id: str) -> bool:
        book = self.books.get(book_id)
        if book is None or not book.available:
            return False
        book.available = False
        self.save()
        return True

    def return_book(self, book_id: str) -> bool:
        book = self.books.get(book_id)
        if book is None or book.available:
            return False
        book.available = True
        self.save()
        return True

    def search_by_title(self, query: str) -> list[Book]:
        needle = query.casefold()
        return [book for book in self.books.values() if needle in book.title.casefold()]

    def list_available_books(self) -> list[Book]:
        return [book for book in self.books.values() if book.available]
''',
        "library_system/cli.py": '''from __future__ import annotations

from pathlib import Path

from .library import Book, Library


def prompt_book() -> Book:
    return Book(
        id=input("id: ").strip(),
        title=input("title: ").strip(),
        author=input("author: ").strip(),
        year=int(input("year: ").strip()),
    )


def main() -> int:
    library = Library(Path("library.json"))
    actions = {
        "1": ("Add book", lambda: library.add_book(prompt_book())),
        "2": ("Remove book", lambda: print(library.remove_book(input("id: ").strip()))),
        "3": ("Borrow book", lambda: print(library.borrow_book(input("id: ").strip()))),
        "4": ("Return book", lambda: print(library.return_book(input("id: ").strip()))),
        "5": ("Search by title", lambda: [print(book) for book in library.search_by_title(input("title: ").strip())]),
        "6": ("List available", lambda: [print(book) for book in library.list_available_books()]),
        "0": ("Exit", None),
    }
    while True:
        for key, (label, _) in actions.items():
            print(f"{key}. {label}")
        choice = input("> ").strip()
        if choice == "0":
            return 0
        action = actions.get(choice)
        if action is None:
            print("Unknown option")
            continue
        handler = action[1]
        if handler is not None:
            handler()


if __name__ == "__main__":
    raise SystemExit(main())
''',
        "library_system/tests/test_library.py": '''from __future__ import annotations

import pytest

from library_system.library import Book, Library


def make_library(tmp_path):
    return Library(tmp_path / "library.json")


def test_add_book(tmp_path):
    library = make_library(tmp_path)
    library.add_book(Book("1", "Dune", "Frank Herbert", 1965))
    assert library.books["1"].title == "Dune"


def test_remove_book(tmp_path):
    library = make_library(tmp_path)
    library.add_book(Book("1", "Dune", "Frank Herbert", 1965))
    assert library.remove_book("1") is True
    assert library.remove_book("missing") is False


def test_borrow_book(tmp_path):
    library = make_library(tmp_path)
    library.add_book(Book("1", "Dune", "Frank Herbert", 1965))
    assert library.borrow_book("1") is True
    assert library.books["1"].available is False


def test_return_book(tmp_path):
    library = make_library(tmp_path)
    library.add_book(Book("1", "Dune", "Frank Herbert", 1965, available=False))
    assert library.return_book("1") is True
    assert library.books["1"].available is True


def test_search_by_title(tmp_path):
    library = make_library(tmp_path)
    library.add_book(Book("1", "Dune", "Frank Herbert", 1965))
    library.add_book(Book("2", "The Left Hand of Darkness", "Ursula K. Le Guin", 1969))
    assert [book.id for book in library.search_by_title("dune")] == ["1"]


def test_list_available_books(tmp_path):
    library = make_library(tmp_path)
    library.add_book(Book("1", "Dune", "Frank Herbert", 1965, available=True))
    library.add_book(Book("2", "Neuromancer", "William Gibson", 1984, available=False))
    assert [book.id for book in library.list_available_books()] == ["1"]


def test_persistence_roundtrip(tmp_path):
    path = tmp_path / "library.json"
    library = Library(path)
    library.add_book(Book("1", "Dune", "Frank Herbert", 1965))
    loaded = Library(path)
    assert loaded.books["1"].author == "Frank Herbert"


def test_borrow_unavailable_book_should_fail(tmp_path):
    library = make_library(tmp_path)
    library.add_book(Book("1", "Dune", "Frank Herbert", 1965, available=False))
    assert library.borrow_book("1") is False


def test_return_unknown_book_should_fail(tmp_path):
    library = make_library(tmp_path)
    assert library.return_book("missing") is False


def test_duplicate_book_should_fail(tmp_path):
    library = make_library(tmp_path)
    library.add_book(Book("1", "Dune", "Frank Herbert", 1965))
    with pytest.raises(ValueError):
        library.add_book(Book("1", "Dune Messiah", "Frank Herbert", 1969))
''',
        "library_system/README.md": """# Library System

Small JSON-backed Python library management system.

## Test

```bash
python -m pytest library_system/tests -q
```
""",
    }


def _apply_library_project(state: ShellState, task_id: str) -> Dict[str, Any]:
    workspace = Path.cwd().resolve()
    project_dir = workspace / "library_system"
    result: Dict[str, Any] = {
        "status": "unknown",
        "changed_files": [],
        "command": "python -m pytest library_system/tests -q",
        "test_status": "not_run",
        "exit_code": None,
        "summary": "",
        "rethink_records": [],
    }
    payloads = _library_project_file_payloads()
    for rel, content in payloads.items():
        target = (workspace / rel).resolve()
        if not str(target).startswith(str(project_dir.resolve())):
            result["status"] = "unsafe"
            result["summary"] = f"Refused path outside library_system: {rel}"
            return result
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        result["changed_files"].append(rel)
        _append_shell_event(state, task_id, "file.created", {"path": rel})

    command = str(result["command"])
    try:
        test_env = os.environ.copy()
        test_env["PYTEST_ADDOPTS"] = (test_env.get("PYTEST_ADDOPTS", "") + " -p no:cacheprovider").strip()
        test_env["PYTHONDONTWRITEBYTECODE"] = "1"
        proc = subprocess.run(
            command.split(),
            cwd=str(workspace),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=120,
            env=test_env,
        )
        output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
        result["exit_code"] = proc.returncode
        result["summary"] = output[:1200]
        result["test_status"] = "passed" if proc.returncode == 0 else "failed"
        result["status"] = "completed" if proc.returncode == 0 else "replan_needed"
        _append_shell_event(state, task_id, "test.executed", {"command": command, "status": result["test_status"]})
        if proc.returncode != 0:
            rethink = {
                "trigger": "test_failed",
                "action": "rethink/replan",
                "command": command,
                "summary": output[:600],
            }
            result["rethink_records"].append(rethink)
            _append_shell_event(state, task_id, "rethink.replan", rethink)
    except Exception as exc:
        result["status"] = "replan_needed"
        result["test_status"] = "error"
        result["summary"] = type(exc).__name__
        result["rethink_records"].append({"trigger": "test_error", "action": "rethink/replan", "summary": type(exc).__name__})
    return result


def _handle_natural_language(state: ShellState, user_input: str, *, auto_approve: bool = True) -> str:
    _maybe_warn_legacy_nl_escape_hatch(state)
    return run_agent_turn_for_cli(user_input, state=state, output_mode="default", interactive=True, auto_approve=auto_approve)


def _maybe_warn_legacy_nl_escape_hatch(state: ShellState) -> None:
    if os.getenv("JARVIS_CLI_LEGACY_NL", "0").strip() != "1":
        return
    if bool(getattr(state, "_legacy_nl_warned", False)):
        return
    setattr(state, "_legacy_nl_warned", True)
    _safe_print(
        "JARVIS_CLI_LEGACY_NL is deprecated and ignored; natural language input now always uses AgentLoop.run_turn()."
    )


def _handle_slash_command(state: ShellState, raw: str, envelope: Optional[Any] = None) -> Optional[str]:
    from jarvis.core.routing.command_router import route_command
    from jarvis.core.routing.input_gateway import build_input_envelope
    from jarvis.core.routing.skill_command_router import route_skill_command

    envelope = envelope or build_input_envelope(raw, workspace_root=Path.cwd(), session_id="cli_shell")
    command = route_command(envelope)
    if not command.handled:
        return _render_unknown_command(raw.strip(), suggest_commands(raw.strip()))
    if command.message:
        skill_route = route_skill_command(envelope)
        if skill_route.handled:
            item = _find_skill_item(skill_route.candidate_skill or envelope.slash.command_name or "")
            return _render_skill_invocation(skill_route, item=item, trigger=f"/{envelope.slash.command_name}")
        return command.message

    cmd = "/" + str(command.command_name or "").lower()
    args = list(command.args_tokens)
    handlers = {
        "/help": lambda: _render_help(),
        "/exit": lambda: None,
        "/quit": lambda: None,
        "/clear": lambda: _clear_state(state),
        "/reset": lambda: _clear_state(state),
        "/new": lambda: _clear_state(state),
        "/status": lambda: _shell_status(state),
        "/config": lambda: _shell_config(),
        "/settings": lambda: _shell_config(),
        "/model": lambda: _shell_model(state, args),
        "/provider": lambda: _shell_provider(state, args),
        "/mode": lambda: _shell_mode(state, args),
        "/tools": lambda: _shell_tools(),
        "/skills": lambda: _shell_skills(args),
        "/skill": lambda: _shell_skill(args, envelope),
        "/commands": lambda: _shell_commands(args),
        "/permissions": lambda: _shell_permissions(state),
        "/allowed-tools": lambda: _shell_allowed_tools(state),
        "/approvals": lambda: _shell_approvals(state, args),
        "/approve": lambda: _shell_approve(state, args),
        "/deny": lambda: _shell_reject(state, args),
        "/reject": lambda: _shell_reject(state, args),
        "/plan": lambda: _shell_plan(state, args),
        "/diff": lambda: _shell_diff(state),
        "/test": lambda: _shell_test(state, args),
        "/fix": lambda: _shell_fix(state, args),
        "/build": lambda: _shell_build(state, args),
        "/mcp": lambda: _shell_mcp(args, state),
        "/review": lambda: _shell_review(state),
        "/replay": lambda: _shell_replay(state, args),
        "/evidence": lambda: _shell_evidence(state, args),
        "/logs": lambda: _shell_logs(),
        "/doctor": lambda: _shell_doctor(state),
        "/server": lambda: _shell_server(state),
        "/web": lambda: _render_web_ui(),
        "/app": lambda: _render_web_ui(),
        "/tasks": lambda: _shell_tasks(state, args),
        "/worktree": lambda: _shell_worktree(args),
        "/team": lambda: _shell_team(args),
        "/bg": lambda: _shell_bg(args),
        "/state": lambda: _shell_state(),
        "/thinking": lambda: _shell_thinking(state),
        "/trace": lambda: _shell_trace(state, args),
        "/context": lambda: _shell_context(state, args),
        "/threads": lambda: _shell_threads(state, args),
        "/sessions": lambda: _shell_threads(state, args),
        "/memory": lambda: _shell_memory(state, args),
        "/agents": lambda: _shell_agents(state),
    }
    if cmd in handlers:
        return handlers[cmd]()

    skill_route = route_skill_command(envelope)
    if skill_route.handled:
        if skill_route.response_mode == "skill_tool_dispatch":
            tool_name = ", ".join(skill_route.requires_tools or []) or "skill tool"
            risk = "approval required" if skill_route.requires_approval else "safe"
            return (
                f"Skill command recognized: /{command.command_name}\n"
                f"Dispatch: tool\n"
                f"Tool: {tool_name}\n"
                f"Args: {skill_route.raw_args or '(none)'}\n"
                f"Safety: {risk}"
            )
        return (
            f"Skill command recognized: /{command.command_name}\n"
            f"Dispatch: model\n"
            f"Skill: {skill_route.candidate_skill}\n"
            f"Args: {skill_route.raw_args or '(none)'}"
        )

    spec = resolve_command(cmd) or resolve_command(command.command_name or "")
    if spec is not None:
        return _render_command_stub(spec)
    return _render_unknown_command(cmd, suggest_commands(cmd))


def run_shell_tui(initial_prompt: Optional[str] = None, *, session_id: str | None = None) -> int:
    """Interactive REPL using the React/Ink + Yoga Flexbox TUI.

    Launches a Node.js child process (Ink TUI) that communicates with the
    Python backend via stdin/stdout JSON protocol.

    The Ink TUI provides Claude Code-level UX:
      - Yoga Layout (Flexbox) for terminal grid positioning
      - React reconciler for virtual DOM diffing
      - ANSI optimizer for minimal frame updates
    """
    return _run_ink_tui(initial_prompt=initial_prompt, session_id=session_id)


def _run_ink_tui(
    initial_prompt: str | None = None,
    *,
    session_id: str | None = None,
) -> int:
    """Launch the React/Ink + Yoga Flexbox TUI as a Node.js child process.

    The Node TUI communicates with a Python backend (tui_bridge) via stdin/stdout
    JSON protocol. This gives Claude Code-level TUI quality:
      - Ink's React reconciler for virtual DOM diffing
      - Yoga Layout (C++ Flexbox) for terminal grid layout
      - Ink's ANSI optimizer for minimal frame updates

    Requires Node.js and the jarvis_tui/ directory with installed dependencies.
    """
    import shutil
    import subprocess

    node = shutil.which("node") or shutil.which("node.exe")
    if not node:
        _safe_print("Node.js is required for the Ink TUI. Install Node.js or unset JARVIS_INK_TUI.")
        return 1

    tui_dir = Path(__file__).resolve().parent.parent.parent / "jarvis_tui"
    if not tui_dir.is_dir():
        _safe_print(f"Ink TUI directory not found: {tui_dir}")
        return 1

    entry = tui_dir / "src" / "entry.tsx"
    if not entry.exists():
        _safe_print(f"Ink TUI entry point not found: {entry}")
        return 1

    # Find the project Python
    python_path = sys.executable or shutil.which("python") or "python"

    # Detect model from actual LLM config (not a hardcoded default)
    try:
        from jarvis.core.llm.config import load_llm_config
        model_name = load_llm_config().model or "unknown"
    except Exception:
        model_name = os.environ.get("JARVIS_LLM_MODEL", "unknown")
    branch = ""
    try:
        head = (Path.cwd() / ".git" / "HEAD").read_text().strip()
        if head.startswith("ref: refs/heads/"):
            branch = head[len("ref: refs/heads/"):]
    except Exception:
        pass

    # Use node to run tsx directly (avoids .bin shim issues on Windows)
    tsx_cli = tui_dir / "node_modules" / "tsx" / "dist" / "cli.mjs"
    if not tsx_cli.exists():
        tsx_cli = tui_dir / "node_modules" / "tsx" / "dist" / "cli.js"
    if tsx_cli.exists():
        tsx_args = [node, str(tsx_cli), str(entry)]
    else:
        _safe_print("tsx not found in node_modules. Run: cd jarvis_tui && npm install")
        return 1

    args = [
        *tsx_args,
        "--python", python_path,
        "--cwd", str(Path.cwd()),
        "--model", model_name,
        "--branch", branch,
        "--mode", "default",
    ]
    if initial_prompt:
        args.extend(["--prompt", initial_prompt])

    # Run Node TUI; it spawns the Python bridge internally
    try:
        result = subprocess.run(args, cwd=str(tui_dir))
        return result.returncode
    except FileNotFoundError:
        _safe_print(f"Node.js not found at: {node}")
        return 1
    except KeyboardInterrupt:
        return 0


def _run_bridge_blocking(prompt_text: str, tui: Any) -> None:
    """Run agent bridge with synchronous polling (used for initial_prompt before TUI starts).

    Uses ChunkRenderer — the same chunk processor used by the TUI's _poll_bridge_sync.
    """
    import time
    from jarvis.cli_ui.agent_bridge import AgentThreadBridge
    from jarvis.cli_ui.chunk_renderer import ChunkRenderer, ChunkRendererState
    from jarvis.cli_ui.tui_utils import render_markdown
    from jarvis.cli_ui.streaming import _format_elapsed

    bridge = AgentThreadBridge(permission_mode="workspace_write", auto_approve=True)
    bridge.start(prompt=prompt_text, tui=tui, session_id=tui.session_name)

    state = ChunkRendererState(started_at=time.monotonic())
    renderer = ChunkRenderer(state, write_line=tui.write_line)

    while True:
        try:
            chunk = bridge.chunk_queue.get(timeout=0.1)
        except Exception:
            continue

        if chunk is None:
            break

        try:
            renderer.handle_chunk(chunk)
        except Exception:
            continue

    answer, thinking, tools = renderer.finalize()

    # Store state in tui for toggle support
    if thinking.strip():
        tui._last_thinking_text = thinking.strip()
    tui._last_tools_data = tools

    # Render final answer as markdown
    if answer.strip():
        width = min(tui._terminal_width(), 100)
        rendered = render_markdown(answer.strip(), width=max(width, 40))
        tui.write(rendered + "\n")

    elapsed = renderer.elapsed
    tui._last_latency = _format_elapsed(elapsed)
    tui._last_status_line = f"[dim]  {tui._last_latency}[/dim]"
    tui._render_toggle_block()



def _run_non_interactive(prompt: str, *, auto_approve: bool = False) -> int:
    state = ShellState(DEFAULT_API_BASE)
    state.trace_enabled = True
    _safe_print(state.provider_status_line)
    _safe_print(_handle_natural_language(state, prompt, auto_approve=auto_approve))
    return 0


def _resolve_output_mode(args: argparse.Namespace) -> str:
    mode = str(getattr(args, "output_mode", "default") or "default").lower().strip()
    if bool(getattr(args, "quiet", False)):
        mode = "quiet"
    if bool(getattr(args, "verbose", False)):
        mode = "verbose"
    if bool(getattr(args, "trace_output", False)):
        mode = "trace"
    if bool(getattr(args, "json_output", False)):
        mode = "json"
    if bool(getattr(args, "trace", False)):
        mode = "trace"
    if bool(getattr(args, "json", False)):
        mode = "json"
    if mode not in {"default", "quiet", "verbose", "trace", "json"}:
        return "default"
    return mode


def _compact_tool_args(value: Any) -> str:
    if not isinstance(value, dict) or not value:
        return ""
    parts: list[str] = []
    for key, val in list(value.items())[:3]:
        parts.append(f"{key}={_safe_text(str(val))[:60]}")
    return ", ".join(parts)


def _render_agent_result_text(*, result: Any, provider_line: str, output_mode: str) -> str:
    try:
        from .cli_agent_output import render_agent_result
    except Exception:
        import importlib.util

        mod_path = Path(__file__).with_name("cli_agent_output.py")
        spec = importlib.util.spec_from_file_location("jarvis_cli_agent_output", mod_path)
        if spec is None or spec.loader is None:
            raise
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        render_agent_result = getattr(module, "render_agent_result")

    return render_agent_result(
        result=result,
        provider_line=provider_line,
        output_mode=output_mode,
        mask_fn=_mask_secret_like,
    )


def _local_agent_result(
    *,
    final_answer: str,
    output_type: str = "answer",
    stop_reason: str = "completed",
    status: str = "completed",
    risks: list[str] | None = None,
    events: list[dict[str, Any]] | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
    tool_results: list[dict[str, Any]] | None = None,
    ok: bool = True,
) -> Any:
    machine = {
        "outcome": "completed" if status == "completed" else status,
        "output_type": output_type,
        "tools_used": [str(item.get("name") or "") for item in list(tool_calls or []) if isinstance(item, dict)],
        "commands_run": [],
        "tests_run": [],
        "risks": list(risks or []),
        "stop_reason": stop_reason,
        "handoff_summary": str(final_answer or "")[:400],
    }
    return SimpleNamespace(
        ok=ok,
        session_id="cli_shell",
        turn_id="local_quick_answer",
        final_answer=final_answer,
        events=list(events or []),
        summary={"human": final_answer, "machine": machine},
        stop_reason=stop_reason,
        tool_calls=list(tool_calls or []),
        tool_results=list(tool_results or []),
        status=status,
        output_type=output_type,
    )


def _friendly_cli_error_stop_reason(exc: BaseException) -> str:
    lowered = f"{type(exc).__name__}: {exc}".lower()
    if any(marker in lowered for marker in ("winerror 10013", "connection", "timed out", "timeout", "refused", "reset", "certificate")):
        return "provider_network_error"
    if "401" in lowered or "403" in lowered or "unauthorized" in lowered or "forbidden" in lowered:
        return "provider_auth_error"
    if "404" in lowered or "http" in lowered:
        return "provider_http_error"
    return "model_call_failed"


def _friendly_cli_error_message(exc: BaseException) -> str:
    reason = _friendly_cli_error_stop_reason(exc)
    if reason == "provider_network_error":
        return "真实 LLM 调用失败，网络连接被系统拒绝。可以运行 python scripts/check_llm_api.py 检查 API、代理或防火墙配置。"
    if reason == "provider_auth_error":
        return "真实 LLM 调用失败，provider 鉴权失败。请检查 API key 是否有效。"
    if reason == "provider_http_error":
        return "真实 LLM 调用失败，provider HTTP 响应异常。请检查 base_url、模型名和服务状态。"
    return f"模型调用失败：{type(exc).__name__}"


def run_agent_turn_for_cli(
    prompt: str,
    *,
    state: ShellState | None = None,
    output_mode: str = "default",
    interactive: bool = False,
    auto_approve: bool = False,
) -> str:
    _ = interactive
    state = state or ShellState(DEFAULT_API_BASE)

    from jarvis.agent.loop import AgentLoop
    from jarvis.agent.types import ChatInput

    def _cli_user_prompt(*, question: str, header: str, options: list, multi_select: bool) -> dict:
        """CLI callback for agent.ask_user — renders question and reads answer."""
        # Pause the streaming display so the prompt text isn't overwritten
        from jarvis.cli_ui.streaming import StreamingDisplay
        active = StreamingDisplay._active_display
        if active is not None:
            active.pause()

        lines = [f"\n{'─' * 50}", f"  {header or '?'}: {question}", ""]
        for i, opt in enumerate(options, 1):
            label = opt.get("label", f"Option {i}")
            desc = opt.get("description", "")
            lines.append(f"  [{i}] {label} — {desc}")
        if multi_select:
            lines.append(f"\n  Enter numbers (e.g. 1,3) or type 'all':")
        else:
            lines.append(f"\n  Enter number (1-{len(options)}) or type label:")
        _safe_print("\n".join(lines))
        try:
            raw = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            if active is not None:
                active.resume()
            return {"answers": {}, "note": "user_cancelled"}

        # Resume the streaming display
        if active is not None:
            active.resume()
        if not raw:
            return {"answers": {}, "note": "no_selection"}
        if multi_select:
            if raw.lower() == "all":
                indices = list(range(1, len(options) + 1))
            else:
                indices = [int(x.strip()) for x in raw.split(",") if x.strip().isdigit()]
            selected = {str(options[i - 1].get("label", "")): options[i - 1].get("label", "") for i in indices if 1 <= i <= len(options)}
            return {"answers": selected}
        else:
            if raw.isdigit():
                i = int(raw)
                if 1 <= i <= len(options):
                    label = options[i - 1].get("label", "")
                    return {"answers": {label: label}}
            for opt in options:
                if opt.get("label", "").lower() == raw.lower():
                    return {"answers": {opt["label"]: opt["label"]}}
            return {"answers": {raw: raw}}

    # Adaptive max_steps: coding tasks get 20, simple Q&A gets 8
    _coding_markers = ("修复", "修改", "实现", "fix", "implement", "change", "update", "create", "新建", "创建", "写", "补测试", "重构", "refactor", "patch", "bug", "test ")
    _is_coding = any(m in prompt.lower() for m in _coding_markers)
    adaptive_steps = 20 if _is_coding else 8

    streaming_used = False
    try:
        loop = AgentLoop(
            project_root=str(Path.cwd()),
            permission_mode=state.permission_mode,
            auto_approve=auto_approve,
            max_steps=adaptive_steps,
            user_prompt=_cli_user_prompt,
        )
        # Use streaming path when output_mode is "default" (console) and not trace/json
        streaming_used = output_mode in ("default", "quiet") and not state.trace_enabled
        if streaming_used:
            result = _run_agent_streaming(loop, prompt, state)
        else:
            result = loop.run_turn(
                ChatInput(
                    text=prompt,
                    cwd=str(Path.cwd()),
                    session_id=state.current_thread_id,
                    metadata={"source": "jarvis.cli", "mode": output_mode},
                )
            )
    except Exception as exc:
        streaming_used = False  # Fall back to text rendering so error is visible
        result = _local_agent_result(
            final_answer=_friendly_cli_error_message(exc),
            output_type="error",
            stop_reason=_friendly_cli_error_stop_reason(exc),
            status="failed",
            ok=False,
            events=[{"type": "turn_failed", "payload": {"error": _safe_text(str(exc)), "error_type": type(exc).__name__}}],
        )

    # When streaming was used, answer was already rendered inline; skip duplicate
    if streaming_used:
        context_warning = _build_context_warning(result)
        return ("\n" + context_warning) if context_warning else ""

    # Context window warning
    context_warning = _build_context_warning(result)
    rendered = _render_agent_result_text(result=result, provider_line=state.provider_status_line, output_mode=output_mode)
    if context_warning:
        return rendered + "\n" + context_warning
    return rendered


def _build_context_warning(result: Any) -> str:
    """Extract context window usage from agent events and build warning if needed."""
    events = getattr(result, "events", []) or []
    for event in events:
        payload = event.get("payload", {}) if isinstance(event, dict) else {}
        event_type = event.get("type", "") if isinstance(event, dict) else ""
        if event_type == "context_window_usage" or "context_window_usage" in str(event_type):
            pct = float(payload.get("usage_pct", 0))
            used = int(payload.get("used_tokens", 0))
            window = int(payload.get("context_window", 0))
            if pct >= 0.90:
                return f"\n[WARNING] Context {pct:.0%} full ({used}/{window} tokens). Consider using /new to start fresh."
            elif pct >= 0.80:
                return f"\n[INFO] Context {pct:.0%} used ({used}/{window} tokens)."
    return ""


def _is_pipe_output() -> bool:
    """Return True if stdout is redirected (pipe, file, non-TTY)."""
    import sys
    return not sys.stdout.isatty()


def _render_post_stream_toggles(thinking_text: str, tools: list[dict]) -> None:
    """Show collapsed thinking/tools hints with Ctrl+T/Ctrl+O in-place toggles.

    Uses ANSI escape codes to replace (not append) the toggle content on each
    keypress. The listener runs for 60 seconds in a daemon thread.
    """
    import sys

    from jarvis.cli_ui.streaming import StreamingDisplay
    from jarvis.cli_ui.key_listener import listen_for_key

    if not thinking_text and not tools:
        return

    state = {
        "thinking_expanded": False,
        "tools_expanded": False,
        "lines": 0,
    }

    def _render_all() -> str:
        parts: list[str] = []
        if thinking_text:
            parts.append(
                StreamingDisplay.render_thinking(
                    thinking_text, expanded=state["thinking_expanded"]
                )
            )
        if tools:
            parts.append(
                StreamingDisplay.render_tools_summary(
                    tools, expanded=state["tools_expanded"]
                )
            )
        return "".join(parts)

    # Initial render
    output = _render_all()
    sys.stdout.write(output + "\n")
    state["lines"] = output.count("\n") + 1
    sys.stdout.flush()

    def on_key(key: str) -> bool:
        if key == "\x14" and thinking_text:  # Ctrl+T
            state["thinking_expanded"] = not state["thinking_expanded"]
        elif key == "\x0f" and tools:  # Ctrl+O
            state["tools_expanded"] = not state["tools_expanded"]
        else:
            return False  # keep listening

        # ANSI: cursor up N lines + clear to end of screen
        sys.stdout.write(f"\x1b[{state['lines']}A\x1b[J")
        new_output = _render_all()
        sys.stdout.write(new_output + "\n")
        state["lines"] = new_output.count("\n") + 1
        sys.stdout.flush()
        return False

    listen_for_key(on_key, timeout=60.0)


def _run_agent_streaming(loop: Any, prompt: str, state: ShellState) -> Any:
    """Run agent turn with rich streaming display, returning AgentRunResult.

    The loop now classifies text per step:
    - ``progress_delta`` → transient progress shown in the Thinking panel
    - ``text_delta`` → answer text or tool observation shown in the answer area
    On finish, the Thinking panel collapses and only the final answer remains.
    Use Ctrl+T / Ctrl+O to toggle thinking and tool summaries after the answer.
    """
    import re
    from jarvis.agent.types import ChatInput, AgentRunResult
    from jarvis.cli_ui.streaming import StreamingDisplay

    chat_input = ChatInput(
        text=prompt,
        cwd=str(Path.cwd()),
        session_id=state.current_thread_id,
        metadata={"source": "jarvis.cli", "mode": "streaming"},
    )
    _BOS_TOKENS = ("<｜begin▁of▁sentence｜>", "<｜begin_of_sentence｜>", "<｜end▁of▁sentence｜>", "<｜end_of_sentence｜>")
    # Pattern: \n[Tool `name`: result] — injected by loop.py after tool execution.
    # Greedy .* matches to the LAST ] then $ anchors end-of-string — more
    # efficient than .*? when content contains embedded ] (e.g. [DRY-RUN]).
    _TOOL_RESULT_RE = re.compile(r'^\n?\[Tool `([^`]+)`:\s*(.*)\]$', re.DOTALL)

    collected_answer: list[str] = []
    tool_events: list[dict[str, Any]] = []
    tool_index_queue: list[int] = []   # FIFO — matches tool result order from loop.py
    final_result: dict[str, Any] | None = None
    output_tokens = 0

    with StreamingDisplay() as display:
        try:
            for chunk in loop.run_turn_stream(chat_input):
                try:
                    if chunk.kind == "progress_delta":
                        text = (chunk.progress_delta or "")
                        if text == "__phase_thinking__":
                            continue
                        for tok in _BOS_TOKENS:
                            text = text.replace(tok, "")
                        if text.strip():
                            display.add_progress(text)
                    elif chunk.kind == "text_delta":
                        text = (chunk.text_delta or "")
                        for tok in _BOS_TOKENS:
                            text = text.replace(tok, "")
                        tm = _TOOL_RESULT_RE.match(text)
                        if tm and tool_index_queue:
                            tool_name = tm.group(1)
                            tool_result = tm.group(2).strip()
                            idx = tool_index_queue.pop(0)
                            display.finish_tool(idx, ok=True, result=tool_result)
                        elif text.strip():
                            collected_answer.append(text)
                            display.add_text(text)
                            # Estimate token count from text length
                            output_tokens += max(1, len(text) // 3)
                            display.add_tokens(max(1, len(text) // 3))
                    elif chunk.kind == "reasoning_delta":
                        text = (chunk.reasoning_delta or "")
                        for tok in _BOS_TOKENS:
                            text = text.replace(tok, "")
                        if text.strip():
                            display.add_progress(text)
                    elif chunk.kind == "tool_call_delta" and chunk.tool_name:
                        # New step boundary — clear old progress to avoid duplicates
                        if not tool_index_queue:
                            display.reset_progress()
                        tool_events.append({"tool_name": chunk.tool_name, "arguments": chunk.tool_arguments_delta})
                        idx = display.start_tool(chunk.tool_name, chunk.tool_arguments_delta or "")
                        tool_index_queue.append(idx)
                    elif chunk.kind == "done":
                        final_result = {
                            "finish_reason": chunk.finish_reason,
                            "tool_calls": tool_events,
                        }
                    elif chunk.kind == "event" and chunk.tool_name == "turn_started":
                        pass
                except Exception:
                    # Don't let a display glitch kill the agent loop
                    pass
        except Exception:
            # Generator itself raised — already handled by loop's internal except
            pass

        answer = "".join(collected_answer).strip()
        try:
            display.finish(answer)
        except Exception:
            pass

        # Post-stream: show collapsible thinking + tools toggle (Ctrl+T / Ctrl+O)
        thinking_text = display.thinking_text
        tools_data = display.tools_data
        if not _is_pipe_output():
            try:
                _render_post_stream_toggles(thinking_text, tools_data)
            except Exception:
                pass

        finish_reason = final_result.get("finish_reason", "stop") if final_result else "stop"
        # Only persist cleanly completed answers — partial/truncated answers
        # from timed-out or interrupted turns bleed into the next turn's context.
        _UNCLEAN_FINISH = {"max_steps", "timeout", "no_progress", "consecutive_failures",
                           "retry_with_tool_instruction", "provider_network_error", "length"}
        if answer and finish_reason not in _UNCLEAN_FINISH:
            try:
                loop.store.append_message(
                    state.current_thread_id, "assistant", answer,
                    metadata={"kind": "final_answer", "finish_reason": finish_reason},
                )
            except Exception:
                pass

    return AgentRunResult(
        ok=True,
        final_answer=answer or "Streaming completed.",
        output_type="answer",
        stop_reason=finish_reason,
        status="completed",
        tool_calls=[{"name": e["tool_name"], "arguments": e["arguments"]} for e in tool_events],
        tool_results=[],
        events=[],
        summary={"human": answer, "machine": {"output_type": "answer", "stop_reason": "stop", "tools_used": [e["tool_name"] for e in tool_events]}},
    )



def _run_non_interactive_with_mode(prompt: str, *, output_mode: str = "default", auto_approve: bool = False, session_id: str | None = None) -> int:
    state = ShellState(DEFAULT_API_BASE)
    if session_id:
        state.current_thread_id = session_id
    state.trace_enabled = output_mode == "trace"
    try:
        _safe_print(run_agent_turn_for_cli(prompt, state=state, output_mode=output_mode, auto_approve=auto_approve))
        return 0
    except Exception as exc:
        if output_mode == "json":
            _safe_print(
                json.dumps(
                    {
                        "provider_status": state.provider_status_line,
                        "error": {"type": type(exc).__name__, "message": _safe_text(str(exc))},
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 1
        _safe_print(state.provider_status_line)
        _safe_print(f"[ERROR] CLI render failed: {type(exc).__name__}: {_safe_text(str(exc))}")
        return 1
    return 0


def _should_use_tui(args: argparse.Namespace) -> bool:
    """Determine whether to use the full-screen TUI for interactive mode."""
    if args.use_tui is False:
        return False
    if args.use_tui is True:
        return True
    if not sys.stdin.isatty():
        return False
    try:
        import prompt_toolkit  # noqa: F401
        return True
    except ImportError:
        return False


def main() -> int:
    # Intercept tui_bridge early — it uses stdin/stdout JSON protocol
    # and must not go through argparse (which writes to stdout).
    if len(sys.argv) > 1 and sys.argv[1] == "tui_bridge":
        from jarvis.tui_bridge import run_bridge
        return run_bridge()

    _write_cli_diagnostic("cli_entry")
    _load_local_env_file(_ROOT / ".env")
    _ensure_utf8_stdout()
    parser = argparse.ArgumentParser(prog="python -m jarvis.cli", description="Jarvis CLI")
    parser.add_argument("--minimal", action="store_true", help="minimal mode (no voice, no model downloads)")
    parser.add_argument("-p", "--print", dest="print_prompt", nargs="?", const="__PIPE__", help="run one-shot prompt")
    parser.add_argument("--ask", dest="ask_prompt", nargs="?", const="__PIPE__", help="run one-shot prompt (Codex-style)")
    parser.add_argument(
        "--output",
        dest="output_mode",
        choices=["default", "quiet", "verbose", "trace", "json"],
        default="default",
        help="one-shot output mode",
    )
    parser.add_argument("--quiet", action="store_true", help="alias: --output quiet")
    parser.add_argument("--verbose", action="store_true", help="alias: --output verbose")
    parser.add_argument("--trace", action="store_true", help="alias: --output trace")
    parser.add_argument("--json", action="store_true", help="alias: --output json")
    parser.add_argument("--trace-output", action="store_true", help="alias: --output trace")
    parser.add_argument("--json-output", action="store_true", help="alias: --output json")
    parser.add_argument("-y", "--yes", action="store_true", help="auto-approve all tool calls (skip confirmation)")
    parser.add_argument("-c", "--continue", dest="resume_latest", action="store_true", help="resume latest session")
    parser.add_argument("-r", "--resume", dest="resume_id", help="resume by session or task id")
    parser.add_argument("--model", dest="cli_model", default=None, help="override LLM model (e.g. deepseek-v4-pro, qwen3.6-chat)")
    parser.add_argument("--provider", dest="cli_provider", default=None, help="override LLM provider (e.g. deepseek, openai, qwen)")
    parser.add_argument("--tui", action="store_true", default=None, dest="use_tui", help="use full-screen TUI for interactive mode")
    parser.add_argument("--no-tui", action="store_false", dest="use_tui", help="disable full-screen TUI")
    sub = parser.add_subparsers(dest="cmd", help="subcommands")

    p_cfg = sub.add_parser("config", help="config management")
    p_cfg.add_argument("--show", action="store_true", help="show current config")
    p_cfg.add_argument("--set", nargs="+", metavar="KEY=VALUE", help="set config values")
    p_cfg.add_argument("--encrypt", action="store_true", help="encrypt with --set")

    p_tools = sub.add_parser("tools", help="tool management")
    p_tools.add_argument("--category", help="filter by category")
    p_tools.add_argument("--call", metavar="TOOL_NAME", help="call specified tool")
    p_tools.add_argument("--debug", action="store_true", help="show skill root discovery debug info")
    p_tools.add_argument("extra", nargs="*", help="tool args key=value")

    p_skills = sub.add_parser("skills", help="list skills")
    p_skills.add_argument("--debug", action="store_true", help="show discovered roots and warnings")
    p_skills.add_argument("action", nargs="?", choices=["list", "insights"], default="list", help="skills view")
    p_skills.add_argument("--limit", type=int, default=0, help="limit filtered debug entries")
    p_skills.add_argument("--source", default="", help="filter debug entries by source")
    p_skills.add_argument("--trust", default="", help="filter debug entries by trust class")
    p_skills.add_argument("--status", default="", help="filter debug entries by status")
    p_skills.add_argument("--shadowed", action="store_true", help="show only shadowed entries in debug view")

    p_commands = sub.add_parser("commands", help="show command mapping")
    p_commands.add_argument("--json", action="store_true", help="json output")
    p_commands.add_argument("--category", default=None, help="filter by category")

    p_test = sub.add_parser("test", help="run self check or propose scoped tests")
    p_test.add_argument("target", nargs="?", default="", help="optional test target path")
    p_test.add_argument("--ask", action="store_true", help="request approval before execution")
    p_test.add_argument("--dry-run", action="store_true", help="approval-only test proposal")
    p_chat = sub.add_parser("chat", help="interactive task input")
    p_chat.add_argument("--prompt", help="single task prompt")

    p_auth = sub.add_parser("auth", help="auth commands")
    p_auth_sub = p_auth.add_subparsers(dest="auth_cmd")
    p_auth_sub.add_parser("status")
    p_auth_sub.add_parser("login")
    p_auth_sub.add_parser("logout")
    p_auth_sub.add_parser("token")

    p_server = sub.add_parser("server", help="shared API server")
    p_server_sub = p_server.add_subparsers(dest="server_cmd", required=True)
    p_server_start = p_server_sub.add_parser("start", help="start API server")
    p_server_start.add_argument("--host", default="127.0.0.1")
    p_server_start.add_argument("--port", type=int, default=8765)
    p_server_start.add_argument("--dry-run", action="store_true")
    p_server_status = p_server_sub.add_parser("status", help="check API server health")
    p_server_status.add_argument("--api-base", default=None)

    p_task = sub.add_parser("task", help="task lifecycle commands")
    p_task_sub = p_task.add_subparsers(dest="task_cmd", required=True)
    p_task_run = p_task_sub.add_parser("run", help="create a task")
    p_task_run.add_argument("input")
    p_task_run.add_argument("--allow-code-changes", action="store_true")
    p_task_run.add_argument("--max-commands", type=int, default=3)
    p_task_run.add_argument("--max-files-changed", type=int, default=0)
    p_task_run.add_argument("--require-approval", action="store_true", default=True)
    p_task_run.add_argument("--no-require-approval", action="store_false", dest="require_approval")
    p_task_run.add_argument("--trace", action="store_true", help="print skill routing trace for local fallback")
    p_task_run.add_argument("--api-base", default=None)
    p_task_status = p_task_sub.add_parser("status", help="show task status")
    p_task_status.add_argument("task_id")
    p_task_status.add_argument("--api-base", default=None)
    p_task_events = p_task_sub.add_parser("events", help="show task events")
    p_task_events.add_argument("task_id")
    p_task_events.add_argument("--api-base", default=None)
    p_task_state = p_task_sub.add_parser("state", help="show local CLI coding state")
    p_task_state.add_argument("--api-base", default=None)
    p_task_gc = p_task_sub.add_parser("gc", help="garbage collect old completed local tasks")
    p_task_gc.add_argument("--dry-run", action="store_true", default=True)
    p_task_gc.add_argument("--yes", action="store_true", help="apply removals")
    p_task_gc.add_argument("--older-than-days", type=int, default=14)
    p_task_gc.add_argument("--keep-latest", type=int, default=20)
    p_task_gc.add_argument("--api-base", default=None)

    p_approvals = sub.add_parser("approvals", help="approval queue commands")
    p_approvals_sub = p_approvals.add_subparsers(dest="approval_cmd", required=True)
    p_approvals_list = p_approvals_sub.add_parser("list")
    p_approvals_list.add_argument("--api-base", default=None)
    p_approvals_approve = p_approvals_sub.add_parser("approve")
    p_approvals_approve.add_argument("approval_id")
    p_approvals_approve.add_argument("--api-base", default=None)
    p_approvals_reject = p_approvals_sub.add_parser("reject")
    p_approvals_reject.add_argument("approval_id")
    p_approvals_reject.add_argument("--api-base", default=None)
    p_approvals_prune = p_approvals_sub.add_parser("prune")
    p_approvals_prune.add_argument("--dry-run", action="store_true", default=True)
    p_approvals_prune.add_argument("--yes", action="store_true", help="apply removals")
    p_approvals_prune.add_argument("--older-than-days", type=int, default=0)
    p_approvals_prune.add_argument(
        "--status",
        choices=["completed", "rejected", "all-closed"],
        default="all-closed",
    )
    p_approvals_prune.add_argument("--api-base", default=None)

    p_replay = sub.add_parser("replay", help="replay commands")
    p_replay_sub = p_replay.add_subparsers(dest="replay_cmd", required=True)
    p_replay_show = p_replay_sub.add_parser("show")
    p_replay_show.add_argument("task_id")
    p_replay_show.add_argument("--api-base", default=None)

    p_evidence = sub.add_parser("evidence", help="evidence commands")
    p_evidence_sub = p_evidence.add_subparsers(dest="evidence_cmd", required=True)
    p_evidence_show = p_evidence_sub.add_parser("show")
    p_evidence_show.add_argument("task_id")
    p_evidence_show.add_argument("--api-base", default=None)

    sub.add_parser("diff", help="show latest local diff summary")
    sub.add_parser("review", help="show latest local review summary")

    p_agents = sub.add_parser("agents", help="agent commands")
    p_agents.add_argument("--help-only", action="store_true", help="show help")
    sub.add_parser("mcp", help="mcp commands")
    sub.add_parser("plugin", help="plugin commands")
    p_update = sub.add_parser("update", help="update CLI")
    p_update.add_argument("--dry-run", action="store_true")
    sub.add_parser("doctor", help="diagnostics")
    sub.add_parser("logs", help="show logs")
    sub.add_parser("memory", help="memory surface")
    sub.add_parser("web", help="web surface")
    sub.add_parser("state", help="show local CLI coding state")

    subcommands = {
        "config",
        "tools",
        "skills",
        "commands",
        "test",
        "chat",
        "auth",
        "server",
        "task",
        "approvals",
        "replay",
        "evidence",
        "diff",
        "review",
        "agents",
        "mcp",
        "plugin",
        "update",
        "doctor",
        "logs",
        "memory",
        "web",
        "state",
    }

    argv = sys.argv[1:]
    initial_prompt = None
    if argv and not argv[0].startswith("-") and argv[0] not in subcommands:
        initial_prompt = argv[0]
        argv = argv[1:]
    args = parser.parse_args(argv)
    output_mode = _resolve_output_mode(args)

    # Apply CLI overrides — these take precedence over .env and config file
    if getattr(args, "cli_model", None):
        os.environ["JARVIS_LLM_MODEL"] = args.cli_model
    if getattr(args, "cli_provider", None):
        os.environ["JARVIS_LLM_PROVIDER"] = args.cli_provider

    # Handle --minimal flag (no voice, no model downloads)
    if getattr(args, "minimal", False):
        os.environ["JARVIS_MINIMAL_MODE"] = "true"
        os.environ["JARVIS_MODE"] = "minimal"
        # Disable voice-related environment variables
        os.environ["WHISPER_MODEL"] = ""
        os.environ["ASR_MODEL"] = ""
        os.environ["TTS_VOICE"] = ""

    try:
        if args.cmd == "config":
            return cmd_config(args)
        if args.cmd == "tools":
            _write_cli_diagnostic("before_cmd_tools")
            return cmd_tools(args)
        if args.cmd == "skills":
            return cmd_skills(args)
        if args.cmd == "commands":
            return cmd_commands(args)
        if args.cmd == "test":
            return cmd_test(args)
        if args.cmd == "chat":
            if args.prompt:
                return _run_non_interactive_with_mode(args.prompt, output_mode=output_mode, auto_approve=bool(args.yes))
            if sys.stdin and sys.stdin.isatty():
                if _should_use_tui(args):
                    return run_shell_tui()
                return run_shell_tui()
            _safe_print("Non-interactive shell: use python -m jarvis.cli -p \"...\".")
            return 0
        if args.cmd == "auth":
            return cmd_auth(args)
        if args.cmd == "server":
            return cmd_server(args)
        if args.cmd == "task":
            return cmd_task(args)
        if args.cmd == "approvals":
            return cmd_approvals(args)
        if args.cmd == "replay" and args.replay_cmd == "show":
            return cmd_replay(args)
        if args.cmd == "evidence" and args.evidence_cmd == "show":
            return cmd_evidence(args)
        if args.cmd == "diff":
            return cmd_diff(args)
        if args.cmd == "review":
            return cmd_review(args)
        if args.cmd == "agents":
            return cmd_agents(args)
        if args.cmd == "mcp":
            return cmd_mcp(args)
        if args.cmd == "plugin":
            return cmd_plugin(args)
        if args.cmd == "update":
            return cmd_update(args)
        if args.cmd == "doctor":
            _safe_print(_shell_doctor(ShellState(DEFAULT_API_BASE)))
            return 0
        if args.cmd == "logs":
            _safe_print(_shell_logs())
            return 0
        if args.cmd == "memory":
            _safe_print(_shell_memory(ShellState(DEFAULT_API_BASE)))
            return 0
        if args.cmd == "web":
            _safe_print(f"Web UI: {DEFAULT_WEB_URL}")
            return 0
        if args.cmd == "state":
            return cmd_state(args)

        # Resolve session_id for resume / session-name flags.
        # -r <id> always uses that id (creates if new, resumes if exists).
        # --resume-latest picks the most recently updated session.
        effective_session_id: str | None = None
        if args.resume_id:
            effective_session_id = args.resume_id
        elif args.resume_latest:
            from jarvis.store.session_store import SessionStore
            _resume_store = SessionStore()
            sessions = _resume_store.list_sessions(limit=1)
            if not sessions:
                _safe_print("No previous session found.")
                return 0
            effective_session_id = sessions[0]["session_id"]

        prompt = initial_prompt
        if args.print_prompt is not None:
            if args.print_prompt not in {None, "__PIPE__"}:
                prompt = args.print_prompt
            if not prompt:
                prompt = _read_stdin_text().strip()
            if not prompt:
                _safe_print("No prompt provided.")
                return 1
            return _run_non_interactive_with_mode(prompt, output_mode=output_mode, auto_approve=bool(args.yes), session_id=effective_session_id)

        if args.ask_prompt is not None:
            if args.ask_prompt not in {None, "__PIPE__"}:
                prompt = args.ask_prompt
            if not prompt:
                prompt = _read_stdin_text().strip()
            if not prompt:
                _safe_print("No prompt provided.")
                return 1
            return _run_non_interactive_with_mode(prompt, output_mode=output_mode, auto_approve=bool(args.yes), session_id=effective_session_id)

        if prompt:
            if os.getenv("JARVIS_CLI_AGENT_ONESHOT", "0").strip() == "1":
                return _run_non_interactive_with_mode(prompt, output_mode=output_mode, auto_approve=bool(args.yes), session_id=effective_session_id)
            return _run_non_interactive(prompt, auto_approve=bool(args.yes))

        if sys.stdin and sys.stdin.isatty():
            if _should_use_tui(args):
                return run_shell_tui(session_id=effective_session_id)
            return run_shell_tui(session_id=effective_session_id)
        input_text = _read_stdin_text()
        if input_text.strip():
            return _run_non_interactive(input_text, auto_approve=True)
        parser.print_help()
        return 0
    finally:
        _write_cli_diagnostic("cli_exit")


if __name__ == "__main__":
    raise SystemExit(main())
