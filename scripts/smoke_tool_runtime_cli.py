#!/usr/bin/env python
"""Smoke test: ToolRuntime CLI integration via classify_for_tool_loop.

Tests the full classify → route pipeline without actual LLM calls.

Expected routing:
  给我讲个笑话       -> chat_answer, no tools
  我现在的目录是什么   -> agent_tool_loop (workspace_status)
  查看skill          -> agent_tool_loop (skill_management)
  列一下当前目录      -> agent_tool_loop (file_listing)
  运行 pytest        -> agent_tool_loop (executor_action), requires_approval
  读取 .env 看看      -> refusal_or_safety_message
  修复 bug           -> agent_tool_loop, requires_approval
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.jarvis.core.cli_response.tool_loop_adapter import classify_for_tool_loop

CASES = [
    ("给我讲个笑话", False, "joke_answer"),
    ("我现在的目录是什么", True, "agent_tool_loop"),
    ("查看skill", True, "agent_tool_loop"),
    ("列一下当前目录", True, "agent_tool_loop"),
    ("运行 pytest", True, "agent_tool_loop"),
    ("读取 .env 看看", False, "refusal_or_safety_message"),
    ("修复 bug", True, "agent_tool_loop"),
]

passed = 0
failed = 0

for user_input, expected_work, expected_mode in CASES:
    result = classify_for_tool_loop(user_input)
    actual_work = result.get("is_work_request", False)
    actual_mode = result.get("response_mode", "")

    ok = (actual_work == expected_work) and (actual_mode == expected_mode)
    status = "PASS" if ok else "FAIL"

    print(f"  [{status}] {user_input!r}")
    print(f"         expected: work={expected_work}, mode={expected_mode}")
    print(f"         actual:   work={actual_work}, mode={actual_mode}")

    if ok:
        passed += 1
    else:
        failed += 1

print(f"\n{'='*60}")
print(f"  ToolRuntime CLI Smoke: {passed} passed, {failed} failed")
print(f"{'='*60}")

sys.exit(0 if failed == 0 else 1)
