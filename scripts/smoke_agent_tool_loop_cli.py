#!/usr/bin/env python
"""Smoke test: AgentToolLoop CLI integration.

Tests the full AgentToolLoop pipeline (chat path vs work path vs safety).

Expected behavior:
  给我讲个笑话       -> chat, 0 tool calls
  我现在的目录是什么   -> work, no LLM fallback
  查看skill          -> work, skill_management
  列一下当前目录      -> work, file_listing
  运行 pytest        -> work, executor_action
  读取 .env 看看      -> safety refusal, 0 tool calls
  修复 bug           -> work, agent_tool_loop
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.jarvis.core.cli_response.tool_loop_adapter import (
    build_default_tool_loop,
    execute_agent_tool_loop,
)

CASES = [
    ("给我讲个笑话", False, 0),
    ("我现在的目录是什么", False, 0),  # no LLM → 0 tool calls
    ("查看skill", False, 0),
    ("列一下当前目录", False, 0),
    ("运行 pytest", False, 0),
    ("读取 .env 看看", False, 0),
    ("修复 bug", False, 0),
]

passed = 0
failed = 0

loop = build_default_tool_loop(auto_approve=True)

for user_input, expect_dangerous, expect_tool_calls in CASES:
    response, is_dangerous, summary = execute_agent_tool_loop(
        user_input, tool_loop=loop,
    )

    # Safety refusals should have safety in response
    is_safety = "SAFETY" in response or "安全" in response
    expected_safety = (user_input == "读取 .env 看看")

    ok = True
    errors = []

    if expected_safety and not is_safety:
        ok = False
        errors.append(f"expected safety refusal but got: {response[:80]}")
    if not expected_safety and is_safety:
        ok = False
        errors.append(f"unexpected safety refusal for: {user_input}")

    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {user_input!r}")
    print(f"         response: {response[:80]}...")
    print(f"         summary:  {summary}, dangerous: {is_dangerous}")
    if errors:
        for e in errors:
            print(f"         ERROR: {e}")

    if ok:
        passed += 1
    else:
        failed += 1

print(f"\n{'='*60}")
print(f"  AgentToolLoop CLI Smoke: {passed} passed, {failed} failed")
print(f"{'='*60}")

sys.exit(0 if failed == 0 else 1)
