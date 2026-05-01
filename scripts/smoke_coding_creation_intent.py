#!/usr/bin/env python
"""Smoke test coding creation intent routing and CLI dispatch."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jarvis import cli as cli_mod
from src.jarvis.core.routing.cli_adapter import build_cli_route

CASES = [
    "在这个工作空间写一个python程序，打印helloworld。",
    "写一个 python 程序打印 helloworld",
    "新建一个 hello.py，打印 hello world",
    "write a python program that prints hello world",
]


def main() -> int:
    failed = 0
    hello_targets = [ROOT / "hello.py", ROOT / "main.py", ROOT / "hello_world.py"]
    before = {str(path): path.exists() for path in hello_targets}

    for text in CASES:
        route_payload = build_cli_route(text, mode="safe", input_kind="unknown_task")
        route = route_payload["route_after_safety"]
        state = cli_mod.ShellState(cli_mod.DEFAULT_API_BASE)
        output = cli_mod._handle_natural_language(state, text)

        if route["intent"] != "coding_task" or route["response_mode"] != "coding_loop":
            failed += 1
            print(f"[FAIL] {text}: wrong route {json.dumps(route, ensure_ascii=False)}")
        if "我需要再确认一下" in output:
            failed += 1
            print(f"[FAIL] {text}: regressed to clarify")
        if "Approval required" not in output:
            failed += 1
            print(f"[FAIL] {text}: missing approval-gated output")
        if route["routing_trace"].get("final_decision") != "coding_task":
            failed += 1
            print(f"[FAIL] {text}: trace missing final coding decision")

    after = {str(path): path.exists() for path in hello_targets}
    if before != after:
        failed += 1
        print("[FAIL] approval gate should block file creation before approval")

    if failed:
        print(f"Smoke failed: {failed}")
        return 1
    print("Coding creation smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
