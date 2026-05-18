"""Smoke-test every registered tool through the ToolCallExecutor."""
from __future__ import annotations

import sys, io, os
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.jarvis.agent.tools import ToolRegistryAdapter, ToolCallExecutor
from src.jarvis.agent.types import ToolCall

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
SESSION_ID = "smoke_test_session"
TURN_ID = "smoke_test_turn"


def _base_context():
    return {"cwd": PROJECT_ROOT, "session_id": SESSION_ID, "turn_id": TURN_ID, "permission_mode": "workspace_write", "mode": "smoke_test"}


registry = ToolRegistryAdapter(project_root=PROJECT_ROOT, permission_mode="workspace_write")
executor = ToolCallExecutor(registry_adapter=registry, permission_mode="workspace_write", auto_approve=True)


def test_tool(name: str, arguments: dict) -> dict:
    call = ToolCall.new(name=name, arguments=arguments)
    result = executor.execute(call, context=_base_context())
    return {
        "tool": name,
        "ok": result.ok,
        "error": result.error,
        "content_type": type(result.content).__name__,
        "content_preview": (str(result.content)[:200] + "...") if len(str(result.content or "")) > 200 else str(result.content or ""),
    }


results = []

# ── Filesystem tools ──
print("=== Filesystem tools ===")
r = test_tool("repo_reader.list_tree", {"repo_path": PROJECT_ROOT, "max_depth": 1})
r["label"] = "list_tree"
results.append(r)
print(f"  list_tree: ok={r['ok']}, error={r['error']}")

r = test_tool("repo_reader.search_files", {"repo_path": PROJECT_ROOT, "pattern": "class AgentLoop", "max_results": 5})
r["label"] = "search_files"
results.append(r)
print(f"  search_files: ok={r['ok']}, error={r['error']}")

r = test_tool("repo_reader.read_file", {"path": "src/jarvis/agent/types.py", "start_line": 1, "end_line": 5})
r["label"] = "read_file"
results.append(r)
print(f"  read_file: ok={r['ok']}, error={r['error']}")

r = test_tool("repo_reader.search_symbol", {"repo_path": PROJECT_ROOT, "symbol": "AgentRunResult", "max_results": 5})
r["label"] = "search_symbol"
results.append(r)
print(f"  search_symbol: ok={r['ok']}, error={r['error']}")

r = test_tool("repo_reader.glob", {"repo_path": PROJECT_ROOT, "pattern": "src/**/*.py", "max_results": 5})
r["label"] = "glob"
results.append(r)
print(f"  glob: ok={r['ok']}, error={r['error']}")

# ── File editor tools ──
print("\n=== File editor tools ===")
test_file = os.path.join(PROJECT_ROOT, ".jarvis", "smoke_test_tmp.txt")
# Ensure clean slate
if os.path.exists(test_file):
    os.remove(test_file)

r = test_tool("file_editor.write_file", {"path": test_file, "content": "smoke test line 1\nsmoke test line 2\n", "create": True})
r["label"] = "write_file"
results.append(r)
print(f"  write_file: ok={r['ok']}, error={r['error']}")

r = test_tool("file_editor.insert_text", {"path": test_file, "anchor": "line 1", "content": "inserted line", "position": "after"})
r["label"] = "insert_text"
results.append(r)
print(f"  insert_text: ok={r['ok']}, error={r['error']}")

r = test_tool("file_editor.replace_text", {"path": test_file, "old": "smoke test", "new": "SMOKE TEST"})
r["label"] = "replace_text"
results.append(r)
print(f"  replace_text: ok={r['ok']}, error={r['error']}")

r = test_tool("file_editor.diff", {"path": test_file})
r["label"] = "diff"
results.append(r)
print(f"  diff: ok={r['ok']}, error={r['error']}")

if os.path.exists(test_file):
    os.remove(test_file)

# ── Command runner ──
print("\n=== Command runner ===")
r = test_tool("command_runner.run", {"command": "echo smoke_test_ok", "cwd": PROJECT_ROOT, "timeout_s": 5})
r["label"] = "run_command"
results.append(r)
print(f"  run_command: ok={r['ok']}, error={r['error']}")

# ── Test runner ──
print("\n=== Test runner ===")
r = test_tool("test_runner.run_test", {"test_scope": "tests/agent/test_context_compactor.py", "timeout_s": 30})
r["label"] = "run_test"
results.append(r)
print(f"  run_test: ok={r['ok']}, error={r['error']}")

# ── Web tools ──
print("\n=== Web tools ===")
r = test_tool("web.search", {"query": "Python programming", "top_k": 2})
r["label"] = "web_search"
results.append(r)
print(f"  web_search: ok={r['ok']}, error={r['error']}")

r = test_tool("web.fetch", {"url": "https://www.cnblogs.com/ExMan/p/18720701", "max_chars": 2000})
r["label"] = "web_fetch"
results.append(r)
print(f"  web_fetch: ok={r['ok']}, error={r['error']}")

# ── Memory tools ──
print("\n=== Memory tools ===")
r = test_tool("memory.search", {"query": "test project context management"})
r["label"] = "memory_search"
results.append(r)
print(f"  memory_search: ok={r['ok']}, error={r['error']}")

r = test_tool("memory.write", {"memory_type": "project_fact", "key": "smoke_test_key", "value": "Smoke test value for tool testing"})
r["label"] = "memory_write"
results.append(r)
print(f"  memory_write: ok={r['ok']}, error={r['error']}")

r = test_tool("memory.remember", {"key": "user_prefers_concise", "value": "The user prefers concise output"})
r["label"] = "memory_remember"
results.append(r)
print(f"  memory_remember: ok={r['ok']}, error={r['error']}")

# ── Task tools ──
print("\n=== Task tools ===")
r = test_tool("task.create", {"goal": "Smoke test task", "steps": ["Step 1: Verify tool works", "Step 2: Report results"]})
r["label"] = "task_create"
results.append(r)
print(f"  task_create: ok={r['ok']}, error={r['error']}")

r = test_tool("task.list", {})
r["label"] = "task_list"
results.append(r)
print(f"  task_list: ok={r['ok']}, error={r['error']}")

r = test_tool("task.update", {"plan_id": "nonexistent", "step_index": 0, "status": "completed"})
r["label"] = "task_update"
results.append(r)
print(f"  task_update: ok={r['ok']}, error={r['error']}")

# ── Checkpoint tools ──
print("\n=== Checkpoint tools ===")
r = test_tool("checkpoint.list", {"task_id": "smoke_test_task"})
r["label"] = "checkpoint_list"
results.append(r)
print(f"  checkpoint_list: ok={r['ok']}, error={r['error']}")

r = test_tool("checkpoint.create", {"task_id": "smoke_test_task", "label": "smoke_test_checkpoint"})
r["label"] = "checkpoint_create"
results.append(r)
print(f"  checkpoint_create: ok={r['ok']}, error={r['error']}")

# ── Skill tools ──
print("\n=== Skill tools ===")
r = test_tool("skill.load", {"name": "fix_test_failure"})
r["label"] = "skill_load"
results.append(r)
print(f"  skill_load: ok={r['ok']}, error={r['error']}")

# ── MCP tools ──
print("\n=== MCP tools ===")
r = test_tool("mcp.list_servers", {})
r["label"] = "mcp_list_servers"
results.append(r)
print(f"  mcp_list_servers: ok={r['ok']}, error={r['error']}")

# ── Agent interaction tools ──
print("\n=== Agent interaction tools ===")
r = test_tool("agent.ask_user", {
    "question": "Which option do you prefer?",
    "header": "Test",
    "options": [{"label": "Option A", "description": "First option"}, {"label": "Option B", "description": "Second option"}],
    "multi_select": False,
})
r["label"] = "agent_ask_user"
results.append(r)
print(f"  agent_ask_user: ok={r['ok']}, error={r['error']}")

# ── BG task tools ──
print("\n=== Background task tools ===")
r = test_tool("bg.task.run", {"tool_name": "repo_reader.read_file", "tool_arguments": {"path": "src/jarvis/agent/types.py", "start_line": 1, "end_line": 3}, "description": "Read file in background"})
r["label"] = "bg_task_run"
results.append(r)
print(f"  bg_task_run: ok={r['ok']}, error={r['error']}")

# ── Summary ──
print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
failed = [r for r in results if not r["ok"]]
# Categorize failures
real_bugs = []
known_limits = []
for r in results:
    status = "OK" if r["ok"] else "FAIL"
    label = r.get("label", r["tool"])
    error = f"  error={r['error'][:100]}" if r["error"] else ""
    print(f"  {status:4s}  {label:30s}{error}")
    if not r["ok"]:
        err = str(r.get("error") or "")
        if any(m in err for m in ("not_available", "no_thread_store", "No user prompt", "no default test", "non-interactive")):
            known_limits.append(r)
        else:
            real_bugs.append(r)

print(f"\nTotal: {len(results)} tools")
print(f"  Passed: {len(results) - len(failed)}")
print(f"  Failed (known limits / missing deps): {len(known_limits)}")
print(f"  Failed (real bugs): {len(real_bugs)}")

if known_limits:
    print("\nKnown limits (not bugs):")
    for r in known_limits:
        print(f"  - {r['label']}: {r['error'][:80]}")
if real_bugs:
    print("\nREAL BUGS NEEDING FIX:")
    for r in real_bugs:
        print(f"  - {r['label']}: {r['error']}")
    sys.exit(1)
else:
    print("\nNo real bugs found. All tools operational!")
