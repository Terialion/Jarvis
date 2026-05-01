"""Smoke script — work path LLM tool selection verification.

Tests that the work path correctly routes through AgentToolLoop with
tool context, even without a real LLM provider.
"""

import os
import sys
import json

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)


def main() -> int:
    """Test work path tool selection without real LLM."""
    from src.jarvis.core.tools.registry import ToolRegistry
    from src.jarvis.core.tools.builtin import register_builtin_tools
    from src.jarvis.core.tools.runtime import ToolRuntime, ApprovalGate
    from src.jarvis.core.tools.loop import AgentToolLoop, LoopResult
    from src.jarvis.core.routing.agent_router import route_agent_request

    reg = ToolRegistry()
    register_builtin_tools(reg)

    runtime = ToolRuntime(
        registry=reg,
        permission_mode="read_only",
        approval_gate=ApprovalGate(auto_approve=False),
    )

    # No LLM provider — work path should return structured acknowledgment
    loop = AgentToolLoop(
        registry=reg,
        runtime=runtime,
        llm_provider=None,
        max_rounds=3,
    )

    print("=" * 60)
    print("  Work Path LLM Tool Selection — Smoke Tests")
    print("=" * 60)

    cases = [
        {
            "input": "我现在的目录是什么",
            "expected_work": True,
            "expected_tools": ["workspace.status"],
            "desc": "workspace_status routing",
        },
        {
            "input": "查看skill",
            "expected_work": True,
            "expected_tools": ["skill.list"],
            "desc": "skill_list routing",
        },
        {
            "input": "列一下当前目录",
            "expected_work": True,
            "expected_tools": ["workspace.list_dir"],
            "desc": "list_dir routing",
        },
        {
            "input": "给我讲个笑话",
            "expected_work": False,
            "expected_tools": [],
            "desc": "chat path — joke",
        },
        {
            "input": "读取 .env",
            "expected_work": False,
            "expected_tools": [],
            "desc": "safety refusal",
        },
        {
            "input": "运行 pytest",
            "expected_work": True,
            "expected_tools": ["shell.run"],
            "desc": "shell.run routing",
        },
    ]

    passed = 0
    failed = 0

    for case in cases:
        inp = case["input"]
        expected_work = case["expected_work"]
        expected_tools = case["expected_tools"]
        desc = case["desc"]

        print(f"\n--- [{inp}] {desc} ---")

        # Route first
        route = route_agent_request(inp)
        result = loop.execute(inp)

        # Check routing
        if route.is_work_request != expected_work:
            print(f"  FAIL: is_work_request={route.is_work_request}, expected={expected_work}")
            failed += 1
            continue

        if expected_work:
            # Verify required_tools contain expected tools
            for t in expected_tools:
                if t not in route.required_tools:
                    print(f"  FAIL: {t} not in required_tools={route.required_tools}")
                    failed += 1
                    break
            else:
                # For work path without LLM, should get structured ack
                if result.error == "safety_refusal":
                    print(f"  WARN: safety_refusal (expected work)")
                    failed += 1
                elif result.response:
                    print(f"  PASS: routed to work, response ok")
                    passed += 1
                else:
                    print(f"  FAIL: empty response")
                    failed += 1
        else:
            # Chat/safety path
            if result.error == "safety_refusal" and "读取 .env" in inp:
                print(f"  PASS: safety refusal")
                passed += 1
            elif not result.error:
                print(f"  PASS: chat path, no tools called")
                passed += 1
            else:
                print(f"  FAIL: unexpected error={result.error}")
                failed += 1

    print(f"\n{'=' * 60}")
    print(f"  Results: {passed} passed, {failed} failed")
    print(f"{'=' * 60}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
