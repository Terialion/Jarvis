#!/usr/bin/env python
"""Input Handling v1 smoke over the golden set."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.jarvis.core.routing.command_router import route_command
from src.jarvis.core.routing.golden_inputs import INPUT_GOLDEN_SET
from src.jarvis.core.routing.hybrid_router import route_user_input
from src.jarvis.core.routing.input_gateway import build_input_envelope
from src.jarvis.core.routing.safety_gate import apply_route_safety
from src.jarvis.core.routing.skill_command_router import route_skill_command


def _run_cli(text: str) -> str:
    proc = subprocess.run(
        [sys.executable, "-m", "jarvis.cli"],
        input=f"{text}\n/exit\n",
        text=True,
        capture_output=True,
        cwd=str(ROOT),
    )
    return (proc.stdout or "") + "\n" + (proc.stderr or "")


def main() -> int:
    failed = 0
    hello_targets = [ROOT / "hello.py", ROOT / "main.py", ROOT / "hello_world.py"]
    before = {str(path): path.exists() for path in hello_targets}

    registry_items = [
        {
            "skill_id": "python-debug",
            "id": "python-debug",
            "description": "Debug Python issues.",
            "metadata": {
                "command_name": "python-debug",
                "command_dispatch": "tool",
                "command_tool": "python_debug_tool",
                "risk_level": "high",
                "user_invocable": True,
            },
        },
        {
            "skill_id": "repo-guide",
            "id": "repo-guide",
            "description": "Guide repo analysis.",
            "metadata": {
                "command_name": "repo-guide",
                "command_dispatch": "model",
                "risk_level": "medium",
                "user_invocable": True,
            },
        },
    ]

    for item in INPUT_GOLDEN_SET:
        text = str(item["input"])
        envelope = build_input_envelope(text, workspace_root=ROOT, session_id="smoke")

        if item.get("expected_kind") == "slash_command":
            route = route_command(envelope)
            if not envelope.slash.is_slash_command:
                failed += 1
                print(f"[FAIL] {text}: not parsed as slash command")
            if envelope.slash.command_name != item.get("expected_command_name"):
                failed += 1
                print(f"[FAIL] {text}: wrong command name {envelope.slash.command_name!r}")
            if "expected_raw_args" in item and envelope.slash.raw_args != item["expected_raw_args"]:
                failed += 1
                print(f"[FAIL] {text}: raw args mismatch {envelope.slash.raw_args!r}")
            if route.entered_llm:
                failed += 1
                print(f"[FAIL] {text}: slash command should not enter LLM")
            continue

        if item.get("expected_kind") == "path":
            if envelope.slash.is_slash_command:
                failed += 1
                print(f"[FAIL] {text}: path misparsed as slash command")
            cli_out = _run_cli(text)
            if "Unknown command" in cli_out:
                failed += 1
                print(f"[FAIL] {text}: path treated as unknown command in CLI")
            continue

        routed = route_user_input(text, source_surface="cli", input_kind="unknown_task", workspace_root=ROOT)
        safe = apply_route_safety(routed, text, mode="safe")
        cli_out = _run_cli(text)

        if safe.response_mode != item["expected_response_mode"]:
            failed += 1
            print(f"[FAIL] {text}: expected mode {item['expected_response_mode']!r}, got {safe.response_mode!r}")
        if item.get("must_not_clarify") and "我需要再确认一下" in cli_out:
            failed += 1
            print(f"[FAIL] {text}: should not clarify")
        if item.get("must_not_enter_task_flow"):
            for forbidden in ("Task task_", "\nPlan\n", "\nResult\n"):
                if forbidden in cli_out:
                    failed += 1
                    print(f"[FAIL] {text}: entered task flow via {forbidden!r}")
                    break
        if item.get("must_not_enter_coding_loop") and "Coding loop complete." in cli_out:
            failed += 1
            print(f"[FAIL] {text}: should not enter coding loop")
        if item.get("must_not_read_sensitive") and safe.response_mode != "refusal_or_safety_message":
            failed += 1
            print(f"[FAIL] {text}: sensitive input not refused")
        if item.get("requires_approval") and safe.requires_approval is not True:
            failed += 1
            print(f"[FAIL] {text}: approval should be required")

    tool_route = route_skill_command(build_input_envelope("/python-debug fix greeting bug"), registry_items=registry_items)
    if not (tool_route.handled and tool_route.response_mode == "skill_tool_dispatch" and tool_route.requires_approval):
        failed += 1
        print("[FAIL] skill command should support tool dispatch with approval gating")

    model_route = route_skill_command(build_input_envelope("/repo-guide inspect repo"), registry_items=registry_items)
    if not (model_route.handled and model_route.response_mode == "skill_agent" and model_route.inject_skill_context):
        failed += 1
        print("[FAIL] skill command should support model dispatch with injected context")

    after = {str(path): path.exists() for path in hello_targets}
    if before != after:
        failed += 1
        print("[FAIL] approval gate should block hello file creation before approval")

    if failed:
        print(f"Smoke failed: {failed}")
        return 1
    print("Input handling smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
