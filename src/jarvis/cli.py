#!/usr/bin/env python
"""Jarvis CLI."""

from __future__ import annotations

import argparse
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

from jarvis.cli_command_map import CliCommandSpec, list_command_specs, render_command_table, resolve_command, suggest_commands

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

DEFAULT_API_BASE = os.getenv("JARVIS_API_BASE", "http://127.0.0.1:8765").rstrip("/")
DEFAULT_WEB_URL = os.getenv("JARVIS_WEB_URL", "http://127.0.0.1:18789")

SHELL_HEADER_TEMPLATE = "Jarvis Code - {mode} - {cwd}"
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
    tasks = dict(state.get("tasks") or {})
    approvals = dict(state.get("approvals") or {})
    pending = [a for a in approvals.values() if str((a or {}).get("status", "")).lower() == "pending"]
    completed_tasks = [t for t in tasks.values() if str((t or {}).get("status", "")).lower() in {"completed", "done"}]
    rejected = [a for a in approvals.values() if str((a or {}).get("status", "")).lower() == "rejected"]
    latest_task_id = str(state.get("latest_task_id") or "")
    latest_approval_id = ""
    if approvals:
        latest_approval_id = sorted(approvals.keys())[-1]
    lines = [
        "CLI Coding State",
        "",
        "Path",
        f"  {_CLI_STATE_PATH.as_posix()}",
        "",
        "Summary",
        f"  schema_version: {state.get('schema_version', _CLI_STATE_SCHEMA_VERSION)}",
        f"  tasks: {len(tasks)}",
        f"  approvals: {len(approvals)}",
        f"  pending_approvals: {len(pending)}",
        f"  completed_tasks: {len(completed_tasks)}",
        f"  rejected_approvals: {len(rejected)}",
        "",
        "Latest",
        f"  task_id: {latest_task_id or '-'}",
        f"  approval_id: {latest_approval_id or '-'}",
    ]
    return "\n".join(lines)


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
    from src.jarvis.ui.app.mock_adapter import AppDataAdapter

    if api_base:
        return AppDataAdapter(base_url=api_base)
    return AppDataAdapter()


def _safe_registry():
    try:
        from jarvis.tools.loader import load_builtin_tools
        from jarvis.tools.registry import ToolRegistry

        registry = ToolRegistry()
        load_builtin_tools(registry)
        return registry
    except Exception:
        return None


def _safe_skill_registry(refresh: bool = False):
    try:
        from src.jarvis.core.skill_harness.registry import get_skill_registry

        return get_skill_registry(_ROOT, refresh=refresh)
    except Exception:
        return None


def _build_provider_status_line() -> tuple[str, Any | None]:
    try:
        from src.jarvis.core.llm.runtime_provider import build_runtime_llm_provider, load_llm_provider_config

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
    mode: str,
    model: str = "unknown",
    provider_status: str = "configured",
    provider_line: str = "",
) -> str:
    lines = [
        SHELL_HEADER_TEMPLATE.format(mode=mode, cwd=cwd),
        f"Model: {model} | Provider: {provider_status} | Web: {DEFAULT_WEB_URL}",
    ]
    if provider_line:
        lines.append(provider_line)
    lines.extend([SHELL_HELP_HINT, "", SHELL_PROMPT])
    return "\n".join(lines)


def _render_help() -> str:
    implemented = [spec for spec in list_command_specs() if spec.name.startswith("/") and spec.status == "implemented"]
    lines = ["Commands:"]
    for spec in implemented:
        aliases = f", {', '.join(spec.aliases)}" if spec.aliases else ""
        lines.append(f"  {spec.name}{aliases:<18} {spec.description}")
    lines.append("")
    lines.append("Use /commands to view full mapping (implemented + skeleton + unsupported).")
    return "\n".join(lines)


def _render_unknown_command(cmd: str, candidates: List[str]) -> str:
    if not candidates:
        return f"Unknown command: {cmd}"
    formatted = []
    for c in candidates:
        formatted.append(c if c.startswith("/") else f"/{c}")
    return f"Unknown command: {cmd}\nDid you mean: {', '.join(formatted)}"


def _render_capabilities(title: str, items: List[Dict[str, str]]) -> str:
    lines = ["=" * 60, f"  {title} ({len(items)})", "=" * 60]
    lines.append("name                         kind        status     source")
    lines.append("--------------------------- ----------- --------- ----------")
    for item in items:
        lines.append(
            f"{(item.get('name') or '')[:27]:<27} {(item.get('kind') or '')[:11]:<11} {(item.get('status') or '')[:9]:<9} {(item.get('source') or '')[:10]:<10}"
        )
    lines.append("=" * 60)
    return "\n".join(lines)


def _render_skill_table(skills: List[Dict[str, Any]], title: str = "Jarvis Skills") -> str:
    lines = [title, "-" * len(title)]
    if not skills:
        lines.append("No skills discovered.")
        return "\n".join(lines)
    lines.append("Name                  Kind      Status      Trust       Source                  Description")
    lines.append("--------------------- --------- ---------- ---------- ----------------------- ------------------------------")
    for skill in skills:
        name = str(skill.get("name") or skill.get("skill_name") or "")[:21]
        kind = str(skill.get("kind") or "skill")[:9]
        status = str(skill.get("status") or "")[:10]
        trust = str(skill.get("trust") or skill.get("metadata", {}).get("trust", {}).get("trust_level", "unknown"))[:10]
        source = str(skill.get("source") or "")[:23]
        description = str(skill.get("description") or "")[:30]
        lines.append(f"{name:<21} {kind:<9} {status:<10} {trust:<10} {source:<23} {description}")
    return "\n".join(lines)


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
    from jarvis.config.manager import init_config

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
        _safe_print(f"\nresult:\n{data_str[:2000]}")
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
        from jarvis.config.manager import init_config

        cfg = init_config()
        checks.append(("config", True, f"schemas={len(cfg.get_schema_names())}"))
    except Exception as exc:
        checks.append(("config", False, type(exc).__name__))
    try:
        from jarvis.tools.loader import load_builtin_tools
        from jarvis.tools.registry import ToolRegistry

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
    from src.jarvis.api.server import run_server

    _safe_print(f"Starting Jarvis API server on {base}")
    run_server(host=args.host, port=args.port)
    return 0


def _new_external_id(prefix: str) -> str:
    return f"{prefix}_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"


def _create_local_coding_task(input_text: str, mode: str, require_approval: bool) -> Dict[str, Any]:
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
    if require_approval or mode in {"safe", "ask"}:
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


def _collect_skill_trace_for_input(input_text: str, mode: str) -> Dict[str, Any]:
    events: List[str] = ["task.created", "input.received", f"policy.checked: {mode}"]
    policy_checked: Dict[str, Any] = {"mode": mode, "network_enabled": False, "safe_mode": mode == "safe"}
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
        from src.jarvis.core.skill_harness.executor import execute_skill
        from src.jarvis.core.skill_harness.selector import select_skills_for_task
        from src.jarvis.core.skill_harness.telemetry import SkillTelemetryStore, SkillUsageRecord

        events.append("skill.registry.loaded")
        selection = select_skills_for_task(
            input_text,
            registry,
            policy={
                "mode": mode,
                "safe_mode": mode == "safe",
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
                    "mode": mode,
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
                mode=mode,
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
        mode = "safe" if bool(getattr(args, "safe", False)) else args.mode
        trace_enabled = bool(getattr(args, "trace", False))
        if trace_enabled:
            trace = _collect_skill_trace_for_input(args.input, mode)
            _safe_print(_render_trace_task_run(args.input, mode, trace))
            return 0
        if _is_coding_fixture_request(args.input) or _is_cli_surface_doc_request(args.input):
            response = _create_local_coding_task(args.input, mode=mode, require_approval=bool(args.require_approval))
            print(json.dumps(response, ensure_ascii=False, indent=2))
            return 0
        adapter = _get_adapter(api_base=_api_base(args))
        payload = {
            "input": args.input,
            "mode": mode,
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
    store = _load_cli_coding_state()
    task_id = str(store.get("latest_task_id") or "")
    if not task_id:
        _safe_print("Diff\n\nChanged files:\n- none\n\nSummary:\n- no local patch recorded")
        return 0
    task = store.get("tasks", {}).get(task_id, {})
    changed = list(task.get("changed_files") or [])
    summary = str(task.get("diff_summary") or "no local patch recorded")
    lines = ["Diff", "", "Changed files:"]
    if not changed:
        lines.append("- none")
    else:
        for item in changed:
            lines.append(f"- {item}")
    lines.extend(["", "Summary:", f"- {summary}"])
    _safe_print("\n".join(lines))
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
        self.mode = "safe"
        self.trace_enabled = False
        self.model = "unknown"
        self.effort = "default"
        self.fast = False
        self.api_base = api_base
        self.tasks: List[Dict[str, Any]] = []
        self.approvals: Dict[str, Dict[str, Any]] = {}
        self.message_count = 0
        self.task_counter = 0
        self.approval_counter = 0
        self.task_records: Dict[str, Dict[str, Any]] = {}
        self.latest_task_id: str = ""
        self.provider_status_line, self.llm_provider = _build_provider_status_line()


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
    state.tasks.append({"task_id": task_id, "input": user_input, "mode": state.mode})
    state.task_records[task_id] = {
        "task_id": task_id,
        "input": user_input,
        "mode": state.mode,
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
    from src.jarvis.core.routing.input_gateway import build_input_envelope

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
    from src.jarvis.core.routing.cli_adapter import build_cli_route

    kind = classify_user_input(user_input)
    result = build_cli_route(user_input, mode="safe", input_kind=kind.value)
    return dict(result.get("route_before_safety") or {})


def _apply_route_safety(route: Dict[str, Any], user_input: str, mode: str) -> Dict[str, Any]:
    from src.jarvis.core.routing.schema import IntentRoute
    from src.jarvis.core.routing.safety_gate import apply_route_safety

    routed = apply_route_safety(IntentRoute(**route), user_input, mode=mode)
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
    from src.jarvis.core.routing.cli_adapter import write_cli_trace

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
    events = ["task.created", "input.received", f"policy.checked: {state.mode}"]
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
            from src.jarvis.core.skill_harness.executor import execute_skill
            from src.jarvis.core.skill_harness.selector import select_skills_for_task
            from src.jarvis.core.skill_harness.telemetry import SkillTelemetryStore, SkillUsageRecord

            events.append("skill.registry.loaded")
            selection = select_skills_for_task(
                user_input,
                registry,
                policy={
                    "mode": state.mode,
                    "network_mode": "disabled",
                    "network_enabled": False,
                    "safe_mode": state.mode == "safe",
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
                        "mode": state.mode,
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
                    mode=state.mode,
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
    result = "Completed in safe mode. No files were modified."
    if selected_skill:
        result = f"Completed in safe mode with skill dry-run: {selected_skill}. {selected_reason}".strip()
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
    return _render_task_output(task_id, state.mode, user_input, plan, events, result, include_events=state.trace_enabled)


def render_conversational_response(kind: InputKind, text: str = "") -> str:
    input_line = f"Input: {text}\n" if text else ""
    if kind == InputKind.GREETING:
        return input_line + (
            "Hello! I am Jarvis, running in safe mode. "
            "You can ask me to inspect the repo, plan a change, route a skill, or use /help for commands."
        )
    if kind == InputKind.CAPABILITY_QUESTION:
        return input_line + "\n".join(
            [
                "I can currently:",
                "- list commands and skills",
                "- route skills deterministically and run safe dry-runs",
                "- plan small code changes",
                "- require approval before patch apply",
                "- show diff, review, replay, and evidence",
                "Use /help to view commands.",
            ]
        )
    if kind == InputKind.CASUAL_CHAT:
        return input_line + "I can help with repo tasks, planning, and safe execution. Use /help to get started."
    return input_line + "I can help, but this looks like a general request. Use /help for commands or describe a repo/task."


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
    mode: str,
    user_input: str,
    plan: List[str],
    events: List[str],
    result: str,
    *,
    include_events: bool = True,
) -> str:
    lines = [f"Task {task_id} - completed - {mode}", "", "Input", f"  {user_input}"]
    if plan:
        lines.append("")
        lines.append("Plan")
        for idx, step in enumerate(plan, 1):
            lines.append(f"  {idx}. {step}")
    if include_events and events:
        lines.append("")
        lines.append("Events")
        for ev in events:
            lines.append(f"  {ev}")
    lines.append("")
    lines.append("Result")
    lines.append(f"  {result}")
    return "\n".join(lines)


def _render_approval(approval_id: str, action: str, reason: str) -> str:
    return "\n".join(
        [
            f"Approval required - {approval_id}",
            "",
            "Action",
            f"  {action}",
            "",
            "Reason",
            f"  {reason}",
            "",
            "Options",
            f"  /approve {approval_id}",
            f"  /reject {approval_id}",
        ]
    )


def _render_command_stub(spec: CliCommandSpec) -> str:
    note = "command recognized; deeper behavior will be expanded incrementally."
    if spec.status == "skeleton":
        note = "command is planned and currently not active beyond safe skeleton routing."
    elif spec.status == "unsupported":
        note = "command is unsupported in current Jarvis CLI and remains disabled."
    return (
        f"{spec.name}\n"
        f"  mapped Claude equivalent: {spec.claude_equivalent or spec.name}\n"
        f"  status: {spec.status}\n"
        f"  safety: {spec.safety}\n"
        f"  note: {note}"
    )


def _shell_config() -> str:
    try:
        from io import StringIO
        from jarvis.config.manager import init_config

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


def _shell_status(state: ShellState) -> str:
    return "\n".join([f"Mode: {state.mode}", f"Model: {state.model}", f"API: {state.api_base}", f"Web: {DEFAULT_WEB_URL}"])


def _shell_permissions(state: ShellState) -> str:
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
    return "\n".join(
        [
            "Policy: safe by default",
            f"Mode: {state.mode}",
            "Dangerous actions require approval or dry-run.",
            f"Skill trust/quarantine enforcement: loaded={total}, quarantined={quarantined}",
        ]
    )


def _shell_allowed_tools(_state: ShellState) -> str:
    lines = ["Allowed tools and skills (safe mode view):"]
    reg = _safe_registry()
    if reg is not None:
        try:
            lines.append("  Tools: " + ", ".join(sorted([t.name for t in reg.list_tools(category=None)])[:12]))
        except Exception:
            lines.append("  Tools: unavailable")
    skill_reg = _safe_skill_registry()
    if skill_reg is not None:
        try:
            snap = skill_reg.snapshot().get("data", {})
            skills = [i.get("id") or i.get("name") for i in list(snap.get("items") or []) if i.get("status") == "available" and not i.get("quarantine")]
            lines.append("  Skills: " + ", ".join(sorted([s for s in skills if s])[:12]))
        except Exception:
            lines.append("  Skills: unavailable")
    return "\n".join(lines)


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
        return "No pending approvals."
    lines = ["Pending approvals:"]
    for approval_id, info in state.approvals.items():
        lines.append(f"  {approval_id}: {info.get('action')}")
    return "\n".join(lines)


def _shell_mode(state: ShellState, args: List[str]) -> str:
    if not args:
        return f"Mode: {state.mode}"
    mode = args[0].lower()
    if mode not in {"safe", "ask", "edit"}:
        return "Usage: /mode <safe|ask|edit>"
    state.mode = mode
    return f"Mode set to {state.mode}"


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
        from src.jarvis.core.skill_harness.telemetry import SkillTelemetryStore

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
    if state.mode in {"safe", "ask"}:
        approval_id = _next_approval_id(state)
        state.approvals[approval_id] = {
            "action": f"{apply_kind}: {target_path}",
            "reason": "File edit requires approval in safe/ask mode.",
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
    apply_result = _apply_coding_fixture_patch() if apply_kind == "edit_file" else _apply_cli_surface_doc_patch()
    if apply_result["ok"]:
        _append_shell_event(state, task_id, "file.modified", {"path": target_path, "changed": apply_result["changed"]})
        _append_shell_event(state, task_id, "patch.applied", {"summary": apply_result["message"]})
        rec = state.task_records.get(task_id, {})
        rec["changed_files"] = [target_path] if apply_result["changed"] else []
        rec["diff_summary"] = apply_result["message"]
        rec.setdefault("evidence", []).append({"kind": "patch_summary", "detail": apply_result["message"]})
    _append_shell_event(state, task_id, "task.completed", {"status": "completed"})
    return apply_result["message"]


def _shell_diff(state: ShellState) -> str:
    task_id = state.latest_task_id
    if not task_id or task_id not in state.task_records:
        return "Diff\n\nChanged files:\n- none\n\nSummary:\n- no local patch recorded"
    record = state.task_records[task_id]
    changed = list(record.get("changed_files") or [])
    summary = record.get("diff_summary") or "no local patch recorded"
    lines = ["Diff", "", "Changed files:"]
    if not changed:
        lines.append("- none")
    else:
        for item in changed:
            lines.append(f"- {item}")
    lines.extend(["", "Summary:", f"- {summary}"])
    _append_shell_event(state, task_id, "diff.generated", {"changed_files": len(changed)})
    return "\n".join(lines)


def _shell_review(state: ShellState) -> str:
    task_id = state.latest_task_id
    if not task_id or task_id not in state.task_records:
        return "Review\n\nChanged files:\n- none\n\nRisk:\nlow\n\nTests:\nnot run"
    record = state.task_records[task_id]
    changed = list(record.get("changed_files") or [])
    tests = dict(record.get("tests") or {})
    risk = "low" if len(changed) <= 1 else "medium"
    test_status = tests.get("status", "not run")
    lines = ["Review", "", "Changed files:"]
    if not changed:
        lines.append("- none")
    else:
        for item in changed:
            lines.append(f"- {item}")
    lines.extend(["", "Risk:", risk, "", "Tests:", str(test_status)])
    _append_shell_event(state, task_id, "review.completed", {"risk": risk, "tests": test_status})
    return "\n".join(lines)


def _shell_logs() -> str:
    lines = ["Logs:"]
    candidates = [str(_ROOT / "logs"), str(_ROOT / "temp" / "cli_stderr_diagnostics.json")]
    for p in candidates:
        if os.path.exists(p):
            lines.append(f"  {p}")
    if len(lines) == 1:
        lines.append("  No logs found.")
    return "\n".join(lines)


def _shell_server(state: ShellState) -> str:
    return f"Server status unknown. Try: python -m jarvis.cli server status (API: {state.api_base})"


def _shell_tasks(state: ShellState, args: Optional[List[str]] = None) -> str:
    if args and args[0].lower() == "gc":
        persistent = _load_cli_coding_state()
        result = _gc_tasks(persistent, older_than_days=14, keep_latest=20, apply_changes=False)
        return json.dumps(result, ensure_ascii=False, indent=2)
    if not state.tasks:
        return "No tasks recorded in this session."
    lines = ["Tasks:"]
    for task in state.tasks:
        lines.append(f"  {task.get('task_id')} - {task.get('input')}")
    return "\n".join(lines)


def _shell_tools() -> str:
    registry = _safe_registry()
    if registry is None:
        return _render_capabilities("Capabilities", _list_builtin_capabilities())
    items = _registry_to_capabilities(registry, "tool")
    if not items:
        items = _list_builtin_capabilities()
    return _render_capabilities("Tools", items)


def _shell_skills(args: Optional[List[str]] = None) -> str:
    args = list(args or [])
    if args and args[0].lower() in {"insights"}:
        return _render_skill_insights()
    debug = bool(args and args[0].lower() in {"debug", "--debug"})
    source_filter = ""
    trust_filter = ""
    status_filter = ""
    shadowed_only = False
    limit = 0
    if debug and len(args) > 1:
        idx = 1
        while idx < len(args):
            token = args[idx].strip().lower()
            if token == "--source" and idx + 1 < len(args):
                source_filter = args[idx + 1]
                idx += 2
                continue
            if token == "--trust" and idx + 1 < len(args):
                trust_filter = args[idx + 1]
                idx += 2
                continue
            if token == "--status" and idx + 1 < len(args):
                status_filter = args[idx + 1]
                idx += 2
                continue
            if token == "--limit" and idx + 1 < len(args):
                try:
                    limit = int(args[idx + 1])
                except Exception:
                    limit = 0
                idx += 2
                continue
            if token == "--shadowed":
                shadowed_only = True
                idx += 1
                continue
            idx += 1
    registry = _safe_skill_registry()
    if registry is None:
        return _render_capabilities("Skills", _list_builtin_capabilities())
    snap = registry.snapshot().get("data", {})
    items = list(snap.get("items") or [])
    if not items:
        return _render_capabilities("Skills", _list_builtin_capabilities())
    table = _render_skill_table(items)
    if debug:
        return table + "\n\n" + _render_skill_debug(
            snap,
            source_filter=source_filter,
            trust_filter=trust_filter,
            status_filter=status_filter,
            shadowed_only=shadowed_only,
            limit=limit,
        )
    return table


def _skill_usage() -> str:
    return "\n".join(
        [
            "Usage: /skill <name> [task]",
            "",
            "Examples:",
            "  /skill list",
            "  /skill show code-generator",
            "  /skill jarvis-code-agent fix greeting bug",
            "",
            "Skill commands keep raw args intact. Write, shell, and network actions stay approval-gated.",
        ]
    )


def _skill_items() -> List[Dict[str, Any]]:
    registry = _safe_skill_registry()
    if registry is None:
        return []
    try:
        return list((registry.snapshot().get("data") or {}).get("items") or [])
    except Exception:
        return []


def _find_skill_item(name: str) -> Optional[Dict[str, Any]]:
    needle = str(name or "").strip().lower()
    if not needle:
        return None
    for item in _skill_items():
        aliases = {
            str(item.get("id") or "").strip().lower(),
            str(item.get("name") or "").strip().lower(),
            str(item.get("skill_id") or "").strip().lower(),
            str(item.get("skill_name") or "").strip().lower(),
        }
        metadata = dict(item.get("metadata") or {})
        aliases.add(str(metadata.get("command_name") or "").strip().lower())
        if needle in aliases:
            return dict(item)
    return None


def _skill_body_has_policy_violation(item: Dict[str, Any]) -> bool:
    candidates = [
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
        return "coding_loop"
    if response_mode == "skill_tool_dispatch":
        return "tool"
    return "skill_agent"


def _render_skill_invocation(skill_route: Any, *, item: Optional[Dict[str, Any]] = None, trigger: str = "/skill") -> str:
    from src.jarvis.core.cli_response.natural_responses import render_refusal_safety

    raw_args = str(getattr(skill_route, "raw_args", "") or "")
    skill_name = str(getattr(skill_route, "candidate_skill", "") or "")
    if _skill_request_is_sensitive(raw_args):
        return render_refusal_safety()
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
            f"Skill: {item.get('skill_id') or item.get('id') or name}",
            f"Status: {item.get('status', '-')}",
            f"Trust: {item.get('trust', '-')}",
            f"Source: {item.get('source', '-')}",
            f"Description: {item.get('description', '-')}",
            "Allowed tools: " + (", ".join([str(t) for t in list(item.get("allowed_tools") or [])]) or "none"),
        ]
    )


def _shell_skill(args: List[str], envelope: Any) -> str:
    from src.jarvis.core.routing.skill_command_router import route_skill_command

    if not args or args[0].lower() in {"help", "--help", "-h"}:
        return _skill_usage()
    action = args[0].lower()
    if action == "list":
        return _shell_skills([])
    if action == "show":
        if len(args) < 2:
            return "Usage: /skill show <name>"
        return _render_skill_show(args[1])

    item = _find_skill_item(args[0])
    if item is None:
        return f"skill-not-found: {args[0]}\nUse /skills to list available skills."
    if str(item.get("status") or "").lower() not in {"enabled", "available"}:
        return f"skill-unavailable: {args[0]}\nStatus: {item.get('status', '-')}"
    skill_route = route_skill_command(envelope)
    if not skill_route.handled:
        return f"skill-not-found: {args[0]}\nUse /skills to list available skills."
    return _render_skill_invocation(skill_route, item=item, trigger=f"/skill {args[0]}")


def _shell_commands(args: List[str]) -> str:
    category = args[0] if args else None
    return render_command_table(list_command_specs(category=category))


def _shell_memory(_state: ShellState) -> str:
    return "Memory: read-only summary mode. Write operations require task/runtime flow."


def _shell_agents(_state: ShellState) -> str:
    return "Agents: plan, explore, implement, review (skeleton routing)."


def _shell_trace(state: ShellState, args: Optional[List[str]] = None) -> str:
    args = list(args or [])
    if not args:
        return f"Trace mode: {'on' if state.trace_enabled else 'off'}"
    token = args[0].strip().lower()
    if token in {"on", "true", "1"}:
        state.trace_enabled = True
        return "Trace mode: on"
    if token in {"off", "false", "0"}:
        state.trace_enabled = False
        return "Trace mode: off"
    return "Usage: /trace [on|off]"


def _shell_state() -> str:
    if not _CLI_STATE_PATH.exists():
        return "No CLI coding state found."
    return _state_summary_text(_load_cli_coding_state())


def _shell_doctor(state: ShellState) -> str:
    lines = ["Doctor report:"]
    try:
        from jarvis.config.manager import init_config

        cfg = init_config()
        lines.append(f"  config schemas: {len(cfg.get_schema_names())}")
    except Exception as exc:
        lines.append(f"  config: unavailable ({_safe_text(type(exc).__name__)})")
    reg = _safe_registry()
    if reg is None:
        lines.append("  tool registry: unavailable")
    else:
        try:
            lines.append(f"  tool registry: {len(reg.list_tools(category=None))} tools")
        except Exception:
            lines.append("  tool registry: error")
    skill_registry = _safe_skill_registry()
    if skill_registry is None:
        lines.append("  skill registry: unavailable")
    else:
        try:
            snap = skill_registry.snapshot().get("data", {})
            discovery = snap.get("discovery", {})
            lines.append(f"  skill registry: {int(snap.get('count', 0))} loaded")
            lines.append(f"  skill roots: {len(list(discovery.get('roots') or []))}")
            lines.append(f"  skill invalid: {len([i for i in list(snap.get('items') or []) if i.get('status') == 'invalid'])}")
            lines.append(f"  skill quarantined: {len([i for i in list(snap.get('items') or []) if i.get('quarantine')])}")
        except Exception:
            lines.append("  skill registry: error")
    try:
        from src.jarvis.core.skill_harness.instructions import load_project_instruction_context

        instruction_ctx = load_project_instruction_context(_ROOT)
        lines.append(f"  instruction sources: {len(instruction_ctx.sources)}")
        lines.append(f"  instruction no_network: {instruction_ctx.no_network}")
        lines.append(f"  instruction docs_only: {instruction_ctx.docs_only}")
    except Exception:
        lines.append("  instruction sources: unavailable")
    lines.append(f"  mode: {state.mode}")
    lines.append(f"  api_base: {state.api_base}")
    return "\n".join(lines)


def _shell_approve(state: ShellState, args: List[str]) -> str:
    if not args:
        return "Usage: /approve <id>"
    approval_id = args[0]
    if approval_id.lower() == "last":
        approval_id = next(reversed(state.approvals), "") if state.approvals else ""
    if approval_id not in state.approvals:
        return f"Approval not found: {args[0]}"
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
            f"Approved: {approval_id}",
            "Library project created.",
            "",
            "Changed files",
        ]
        lines.extend([f"  - {item}" for item in list(apply_result.get("changed_files") or [])] or ["  - none"])
        lines.extend(
            [
                "",
                "Scoped test command",
                f"  {apply_result.get('command')}",
                "",
                "Test status",
                f"  {apply_result.get('test_status')}",
            ]
        )
        if apply_result.get("rethink_records"):
            lines.extend(["", "Rethink/Replan"])
            lines.extend([f"  - {item.get('trigger')}: {item.get('action')}" for item in apply_result["rethink_records"]])
        if apply_result.get("summary"):
            lines.extend(["", "Test output", str(apply_result.get("summary"))[:1200]])
        return "\n".join(lines)
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
        return f"Approved: {approval_id}\n{apply_result.get('message', '')}".strip()
    if kind == "run_test":
        command = str(info.get("command") or "python -m pytest examples/coding_fixture -q")
        result = {"status": "dry_run", "command": command, "exit_code": None, "summary": "dry-run only"}
        if task_id in state.task_records:
            _append_shell_event(state, task_id, "approval.resolved", {"approval_id": approval_id, "decision": "approved"})
        if state.mode == "edit":
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
        return f"Approved: {approval_id}\nTest status: {result['status']}\nCommand: {command}"
    return f"Approved: {approval_id}"


def _shell_reject(state: ShellState, args: List[str]) -> str:
    if not args:
        return "Usage: /reject <id>"
    approval_id = args[0]
    if approval_id.lower() == "last":
        approval_id = next(reversed(state.approvals), "") if state.approvals else ""
    if approval_id not in state.approvals:
        return f"Approval not found: {args[0]}"
    info = dict(state.approvals.pop(approval_id, {}))
    task_id = str(info.get("task_id") or "")
    if task_id in state.task_records:
        _append_shell_event(state, task_id, "approval.resolved", {"approval_id": approval_id, "decision": "rejected"})
    return f"Rejected: {approval_id}"


def _shell_replay(state: ShellState, args: List[str]) -> str:
    task_id = args[0] if args else state.latest_task_id
    if task_id and task_id in state.task_records:
        record = state.task_records[task_id]
        lines = ["Replay", "", f"Task: {task_id}", "Events:"]
        for event in list(record.get("events") or []):
            lines.append(f"  {event.get('type')}")
        return "\n".join(lines)
    if not task_id:
        return "Replay unavailable: no task selected."
    try:
        res = _get_adapter().get_task_replay(task_id)
        if res.ok:
            return json.dumps(res.data, ensure_ascii=False, indent=2)
        return f"Replay unavailable for {task_id}"
    except Exception as exc:
        return f"Replay error: {_safe_text(type(exc).__name__)}"


def _shell_evidence(state: ShellState, args: List[str]) -> str:
    task_id = args[0] if args else state.latest_task_id
    if task_id and task_id in state.task_records:
        record = state.task_records[task_id]
        lines = ["Evidence", "", f"Task: {task_id}", "Items:"]
        for item in list(record.get("evidence") or []):
            kind = item.get("kind", "unknown")
            lines.append(f"  - {kind}")
        return "\n".join(lines)
    if not task_id:
        return "Evidence unavailable: no task selected."
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
    return "Context cleared."


def _run_repo_inspection(user_input: str) -> Dict[str, Any]:
    from src.jarvis.core.repo_inspection import RepoInspectionRequest, inspect_repo

    result = inspect_repo(
        RepoInspectionRequest(
            workspace_root=Path.cwd(),
            user_input=user_input,
        ),
        session_id="cli_shell",
    )
    return result.to_dict()


def _run_coding_loop(user_input: str) -> Dict[str, Any]:
    from src.jarvis.core.coding_loop.orchestrator import run_coding_loop

    return run_coding_loop(
        user_input,
        Path.cwd(),
        max_rounds=3,
        auto_approve=False,
    )


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
            {"type": "coding_loop.entered", "detail": {"requires_write": True, "requires_shell": True}, "ts": _iso_now()},
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


def _handle_natural_language(state: ShellState, user_input: str) -> str:
    from src.jarvis.core.cli_response.dispatcher import dispatch_natural_language
    from src.jarvis.core.cli_response.tool_loop_adapter import (
        build_default_tool_loop,
        execute_agent_tool_loop,
    )
    from src.jarvis.core.llm.prompt_builder import generate_chat_response

    route_before = _detect_intent_route(user_input)
    route_after = _apply_route_safety(route_before, user_input, state.mode)
    if route_after.get("response_mode") == "coding_loop" and _is_library_project_request(user_input):
        response = _queue_library_project_approval(state, user_input)
        _append_intent_route_trace(
            state=state,
            user_input=user_input,
            route_before_safety=route_before,
            route_after_safety=route_after,
            final_response_mode="coding_loop",
            entered_task_flow=True,
            notes="library project approval gate",
        )
        return response

    # Build AgentToolLoop once per session and reuse
    if not hasattr(state, "_agent_tool_loop"):
        try:
            state._agent_tool_loop = build_default_tool_loop(
                permission_mode="workspace_write" if state.mode in {"edit", "ask"} else "read_only",
                auto_approve=False,
                llm_provider=state.llm_provider,
                max_rounds=10,
            )
        except Exception:
            state._agent_tool_loop = None

    response, entered_task_flow, final_response_mode, notes = dispatch_natural_language(
        user_input=user_input,
        route_after_safety=route_after,
        run_existing_task_flow=lambda text: _run_existing_task_flow(state, text),
        run_skill_admin=lambda: _shell_skills([]),
        run_repo_inspection=lambda text: _run_repo_inspection(text),
        run_coding_loop=lambda text: _run_coding_loop(text),
        run_agent_tool_loop=lambda text: execute_agent_tool_loop(
            text,
            tool_loop=state._agent_tool_loop,
            permission_mode="workspace_write" if state.mode in {"edit", "ask"} else "read_only",
        ),
        run_llm_chat=lambda text, mode: generate_chat_response(
            user_input=text,
            chat_type=mode,
            llm_provider=state.llm_provider,
        ),
        llm_provider_available=state.llm_provider is not None,
    )
    _append_intent_route_trace(
        state=state,
        user_input=user_input,
        route_before_safety=route_before,
        route_after_safety=route_after,
        final_response_mode=final_response_mode,
        entered_task_flow=entered_task_flow,
        notes=notes,
    )
    return response


def _handle_slash_command(state: ShellState, raw: str, envelope: Optional[Any] = None) -> Optional[str]:
    from src.jarvis.core.routing.command_router import route_command
    from src.jarvis.core.routing.input_gateway import build_input_envelope
    from src.jarvis.core.routing.skill_command_router import route_skill_command

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
        "/tools": lambda: _shell_tools(),
        "/skills": lambda: _shell_skills(args),
        "/skill": lambda: _shell_skill(args, envelope),
        "/commands": lambda: _shell_commands(args),
        "/permissions": lambda: _shell_permissions(state),
        "/allowed-tools": lambda: _shell_allowed_tools(state),
        "/approvals": lambda: _shell_approvals(state, args),
        "/approve": lambda: _shell_approve(state, args),
        "/reject": lambda: _shell_reject(state, args),
        "/mode": lambda: _shell_mode(state, args),
        "/plan": lambda: _shell_plan(state, args),
        "/diff": lambda: _shell_diff(state),
        "/test": lambda: _shell_test(state, args),
        "/fix": lambda: _shell_fix(state, args),
        "/review": lambda: _shell_review(state),
        "/replay": lambda: _shell_replay(state, args),
        "/evidence": lambda: _shell_evidence(state, args),
        "/logs": lambda: _shell_logs(),
        "/doctor": lambda: _shell_doctor(state),
        "/server": lambda: _shell_server(state),
        "/web": lambda: f"Web UI: {DEFAULT_WEB_URL}",
        "/app": lambda: f"Web UI: {DEFAULT_WEB_URL}",
        "/tasks": lambda: _shell_tasks(state, args),
        "/state": lambda: _shell_state(),
        "/trace": lambda: _shell_trace(state, args),
        "/memory": lambda: _shell_memory(state),
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


def run_shell(initial_prompt: Optional[str] = None) -> int:
    from src.jarvis.core.routing.input_gateway import build_input_envelope

    state = ShellState(DEFAULT_API_BASE)
    _safe_print(_render_shell_header(os.getcwd(), state.mode, state.model, provider_line=state.provider_status_line))
    if initial_prompt:
        if os.getenv("JARVIS_CLI_LEGACY_NL", "0").strip() == "1":
            _safe_print("\n" + _handle_natural_language(state, initial_prompt))
        else:
            _safe_print("\n" + run_agent_turn_for_cli(initial_prompt, state=state, output_mode="default", interactive=True))
    while True:
        try:
            line = input(SHELL_PROMPT)
        except (EOFError, KeyboardInterrupt):
            _safe_print("\nbye")
            return 0
        if line is None:
            continue
        raw = line.rstrip("\n")
        if not raw.strip():
            continue
        envelope = build_input_envelope(raw, workspace_root=Path.cwd(), session_id="cli_shell")
        if envelope.slash.is_slash_command:
            result = _handle_slash_command(state, raw, envelope=envelope)
            if result is None:
                return 0
            _safe_print("\n" + result)
            continue
        if os.getenv("JARVIS_CLI_LEGACY_NL", "0").strip() == "1":
            _safe_print("\n" + _handle_natural_language(state, raw))
        else:
            _safe_print("\n" + run_agent_turn_for_cli(raw, state=state, output_mode="default", interactive=True))


def run_shell_from_text(input_text: str) -> int:
    from src.jarvis.core.routing.input_gateway import build_input_envelope

    state = ShellState(DEFAULT_API_BASE)
    _safe_print(_render_shell_header(os.getcwd(), state.mode, state.model, provider_line=state.provider_status_line))
    for raw in (input_text or "").splitlines():
        if not raw.strip():
            continue
        envelope = build_input_envelope(raw, workspace_root=Path.cwd(), session_id="cli_shell")
        if envelope.slash.is_slash_command:
            result = _handle_slash_command(state, raw, envelope=envelope)
            if result is None:
                return 0
            _safe_print("\n" + result)
            continue
        if os.getenv("JARVIS_CLI_LEGACY_NL", "0").strip() == "1":
            _safe_print("\n" + _handle_natural_language(state, raw))
        else:
            _safe_print("\n" + run_agent_turn_for_cli(raw, state=state, output_mode="default", interactive=True))
    return 0


def _run_non_interactive(prompt: str) -> int:
    state = ShellState(DEFAULT_API_BASE)
    state.trace_enabled = True
    _safe_print(state.provider_status_line)
    _safe_print(_handle_natural_language(state, prompt))
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


def _local_model_answer(state: ShellState) -> str:
    line = str(state.provider_status_line or "")
    model = re.search(r"model=([^\s]+)", line)
    provider = re.search(r"LLM provider:\s*([^\s]+)", line)
    base = re.search(r"base_url=([^\s]+)", line)
    key_present = "api_key=present" in line
    key_state_text = "\u5df2\u914d\u7f6e" if key_present else "\u672a\u914d\u7f6e"
    return (
        f"\u5f53\u524d\u914d\u7f6e\u7684 LLM \u662f {model.group(1) if model else 'unknown'}\uff0c"
        f"provider \u662f {provider.group(1) if provider else 'unknown'}\uff0c"
        f"base_url \u662f {base.group(1) if base else 'unknown'}\uff0c"
        f"API key {key_state_text}\u3002"
    )


def _local_capability_answer() -> str:
    return (
        "\u53ef\u4ee5\u3002\u6211\u53ef\u4ee5\u8bfb\u53d6\u548c\u89e3\u91ca\u5f53\u524d\u9879\u76ee\u3001\u641c\u7d22\u4ee3\u7801\u3001\u751f\u6210\u4fee\u6539\u65b9\u6848\uff0c"
        "\u5728\u5b89\u5168\u5ba1\u6279\u540e\u4fee\u6539\u6587\u4ef6\uff0c\u5e76\u8fd0\u884c\u6d4b\u8bd5\u603b\u7ed3\u7ed3\u679c\u3002"
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


def _quick_agent_result_for_cli(prompt: str, state: ShellState) -> Any | None:
    if _looks_like_sensitive_or_dangerous(prompt):
        return _local_agent_result(
            final_answer="不能直接打印 .env 或 API key，因为其中可能包含敏感凭据。",
            output_type="refusal",
            stop_reason="safety_refusal",
            risks=["sensitive_env_requested", "secret_requested"],
        )
    if _looks_like_model_question(prompt):
        return _local_agent_result(final_answer=_local_model_answer(state), output_type="answer")
    if _looks_like_capability_question(prompt):
        return _local_agent_result(final_answer=_local_capability_answer(), output_type="answer")
    if _looks_like_greeting(prompt):
        return _local_agent_result(
            final_answer="你好，我在。可以帮你阅读项目、解释代码、规划修改，并在需要审批时安全地执行工具任务。",
            output_type="answer",
        )
    return None


def _looks_like_model_question(text: str) -> bool:
    low = (text or "").lower()
    return any(
        t in low
        for t in (
            "\u4f60\u662f\u4ec0\u4e48\u6a21\u578b",
            "\u5f53\u524d\u6a21\u578b\u662f\u4ec0\u4e48",
            "\u4f60\u7528\u7684\u662f\u4ec0\u4e48\u6a21\u578b",
            "浣犳槸浠€涔堟ā鍨",
            "褰撳墠妯″瀷鏄粈涔",
            "浣犵敤鐨勬槸浠€涔堟ā鍨",
            "what model",
            "which model",
        )
    )


def _looks_like_capability_question(text: str) -> bool:
    low = (text or "").lower()
    return any(
        t in low
        for t in (
            "\u4f60\u80fd\u5e2e\u6211\u5199\u4ee3\u7801\u5417",
            "\u4f60\u4f1a\u5199\u4ee3\u7801\u5417",
            "\u4f60\u80fd\u505a\u4ec0\u4e48",
            "浣犺兘甯垜鍐欎唬鐮佸悧",
            "浣犱細鍐欎唬鐮佸悧",
            "浣犺兘鍋氫粈涔",
            "what can you do",
            "can you code",
        )
    )


def _looks_like_identity_question(text: str) -> bool:
    low = (text or "").lower()
    return any(
        t in low
        for t in (
            "\u4f60\u662f\u8c01",
            "\u4f60\u662f\u4ec0\u4e48",
            "浣犳槸璋",
            "浣犳槸浠€涔",
            "who are you",
            "what are you",
        )
    )


def _looks_like_greeting(text: str) -> bool:
    low = (text or "").lower().strip()
    return low in {
        "hi",
        "hello",
        "hey",
        "good morning",
        "good afternoon",
        "good evening",
        "\u4e0b\u5348\u597d",
        "\u665a\u4e0a\u597d",
        "\u65e9\u4e0a\u597d",
        "\u4f60\u597d",
        "涓嬪崍濂",
        "鏅氫笂濂",
        "鏃╀笂濂",
        "浣犲ソ",
    }


def _looks_like_joke_request(text: str) -> bool:
    low = (text or "").lower()
    return "\u7b11\u8bdd" in text or "绗戣瘽" in text or "joke" in low


def _looks_like_sensitive_or_dangerous(text: str) -> bool:
    low = (text or "").lower()
    if any(t in low for t in (".env", "jarvis_llm_api_key", "api key", "token", "id_rsa", "password", "secret")):
        return True
    if ("curl " in low or "wget " in low) and ("| sh" in low or "| bash" in low):
        return True
    if "invoke-webrequest" in low and ("| iex" in low or "invoke-expression" in low):
        return True
    if "rm -rf" in low or "\u5220\u9664\u6574\u4e2a\u9879\u76ee" in text:
        return True
    return False


def _looks_like_work_request(text: str) -> bool:
    low = (text or "").lower()
    markers = (
        "\u8bfb\u53d6",
        "readme",
        "read file",
        "\u5217\u4e00\u4e0b\u5f53\u524d\u76ee\u5f55",
        "鍒椾竴涓嬪綋鍓嶇洰褰",
        "current directory",
        "run pytest",
        "\u8fd0\u884c pytest",
        "fix ",
        "\u4fee\u590d",
        "modify",
        "\u4fee\u6539",
        "\u6d4b\u8bd5",
    )
    return any(m in low for m in markers)


def run_agent_turn_for_cli(
    prompt: str,
    *,
    state: ShellState | None = None,
    output_mode: str = "default",
    interactive: bool = False,
) -> str:
    state = state or ShellState(DEFAULT_API_BASE)
    if _looks_like_sensitive_or_dangerous(prompt):
        return "Jarvis\n这个请求涉及敏感信息或危险操作，不能直接执行。"
    from src.jarvis.agent.loop import AgentLoop
    from src.jarvis.agent.types import ChatInput

    loop = AgentLoop(
        project_root=str(_ROOT),
        permission_mode="workspace_write" if state.mode in {"edit", "ask"} else "read_only",
        auto_approve=False,
    )
    result = loop.run_turn(
        ChatInput(
            text=prompt,
            cwd=str(Path.cwd()),
            session_id="cli_shell",
            metadata={"source": "jarvis.cli", "mode": output_mode},
        )
    )
    rendered = _render_agent_result_text(result=result, provider_line=state.provider_status_line, output_mode=output_mode)
    final_answer = str(getattr(result, "final_answer", "") or "")
    has_provider_failure = "无法连接 LLM" in rendered
    if not interactive:
        return rendered
    if final_answer and not has_provider_failure:
        return rendered
    # interactive fallback for model/capability Q should be direct, not generic clarify/network noise
    if _looks_like_model_question(prompt):
        return "Jarvis\n" + _local_model_answer(state)
    if _looks_like_identity_question(prompt):
        return "Jarvis\n\u6211\u662f Jarvis\uff0c\u672c\u5730\u5f00\u53d1\u52a9\u624b\u3002\u6211\u53ef\u4ee5\u5e2e\u4f60\u8bfb\u9879\u76ee\u3001\u89c4\u5212\u4fee\u6539\u3001\u5728\u5ba1\u6279\u540e\u6267\u884c\u6539\u52a8\u548c\u6d4b\u8bd5\u3002"
    if _looks_like_capability_question(prompt):
        return "Jarvis\n" + _local_capability_answer()
    if _looks_like_greeting(prompt):
        return "Jarvis\nHi, I’m here. I can inspect repositories, explain code, plan changes, and run approved tests."
    if _looks_like_joke_request(prompt):
        return "Jarvis\n\u4e3a\u4ec0\u4e48\u7a0b\u5e8f\u5458\u559c\u6b22\u6df1\u591c\u4fee bug\uff1f\u56e0\u4e3a\u767d\u5929 bug \u4f1a\u88c5\u4f5c\u9700\u6c42\u3002"
    if _looks_like_work_request(prompt):
        return "Jarvis\n[WORK] 无法连接 LLM，未执行工具。请检查网络后重试。"
    return rendered


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
) -> str:
    _ = interactive
    state = state or ShellState(DEFAULT_API_BASE)
    quick_result = _quick_agent_result_for_cli(prompt, state)
    if quick_result is not None:
        return _render_agent_result_text(result=quick_result, provider_line=state.provider_status_line, output_mode=output_mode)

    from src.jarvis.agent.loop import AgentLoop
    from src.jarvis.agent.types import ChatInput

    try:
        loop = AgentLoop(
            project_root=str(_ROOT),
            permission_mode="workspace_write" if state.mode in {"edit", "ask"} else "read_only",
            auto_approve=False,
        )
        result = loop.run_turn(
            ChatInput(
                text=prompt,
                cwd=str(Path.cwd()),
                session_id="cli_shell",
                metadata={"source": "jarvis.cli", "mode": output_mode},
            )
        )
    except Exception as exc:
        result = _local_agent_result(
            final_answer=_friendly_cli_error_message(exc),
            output_type="error",
            stop_reason=_friendly_cli_error_stop_reason(exc),
            status="failed",
            ok=False,
            events=[{"type": "turn_failed", "payload": {"error": _safe_text(str(exc)), "error_type": type(exc).__name__}}],
        )
    return _render_agent_result_text(result=result, provider_line=state.provider_status_line, output_mode=output_mode)


def _run_non_interactive_with_mode(prompt: str, *, output_mode: str = "default") -> int:
    state = ShellState(DEFAULT_API_BASE)
    state.trace_enabled = output_mode == "trace"
    try:
        _safe_print(run_agent_turn_for_cli(prompt, state=state, output_mode=output_mode))
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


def main() -> int:
    _write_cli_diagnostic("cli_entry")
    _load_local_env_file(_ROOT / ".env")
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
    parser.add_argument("-c", "--continue", dest="resume_latest", action="store_true", help="resume latest session")
    parser.add_argument("-r", "--resume", dest="resume_id", help="resume by session or task id")
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
    p_task_run.add_argument("--mode", default="safe")
    p_task_run.add_argument("--safe", action="store_true", help="alias for --mode safe")
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
                return _run_non_interactive_with_mode(args.prompt, output_mode=output_mode)
            if sys.stdin and sys.stdin.isatty():
                return run_shell()
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

        if args.resume_latest:
            _safe_print("No previous session found.")
            return 0
        if args.resume_id:
            _safe_print(f"Session not found: {args.resume_id}")
            return 0

        prompt = initial_prompt
        if args.print_prompt is not None:
            if args.print_prompt not in {None, "__PIPE__"}:
                prompt = args.print_prompt
            if not prompt:
                prompt = _read_stdin_text().strip()
            if not prompt:
                _safe_print("No prompt provided.")
                return 1
            return _run_non_interactive_with_mode(prompt, output_mode=output_mode)

        if args.ask_prompt is not None:
            if args.ask_prompt not in {None, "__PIPE__"}:
                prompt = args.ask_prompt
            if not prompt:
                prompt = _read_stdin_text().strip()
            if not prompt:
                _safe_print("No prompt provided.")
                return 1
            return _run_non_interactive_with_mode(prompt, output_mode=output_mode)

        if prompt:
            if os.getenv("JARVIS_CLI_AGENT_ONESHOT", "0").strip() == "1":
                return _run_non_interactive_with_mode(prompt, output_mode=output_mode)
            return _run_non_interactive(prompt)

        if sys.stdin and sys.stdin.isatty():
            return run_shell()
        input_text = _read_stdin_text()
        if input_text.strip():
            return run_shell_from_text(input_text)
        parser.print_help()
        return 0
    finally:
        _write_cli_diagnostic("cli_exit")


if __name__ == "__main__":
    raise SystemExit(main())
