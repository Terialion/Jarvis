"""Diagnostic: trace the full agent pipeline for a user query.

Simulates: user input → context → model call → tool execution → response display.
Shows exactly what happens at each step, including all chunk types received.
"""
import sys
import json
import os
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from jarvis.agent.loop import AgentLoop
from jarvis.agent.types import ChatInput

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)


def test_query(query: str, label: str) -> None:
    print(f"\n{'='*70}")
    print(f"  QUERY: {query}")
    print(f"{'='*70}")

    loop = AgentLoop(
        project_root=PROJECT_ROOT,
        max_steps=3,
        timeout_s=60,
        permission_mode="workspace_write",
        auto_approve=True,
    )

    chat_input = ChatInput(
        text=query,
        cwd=PROJECT_ROOT,
        session_id="diag_session",
        metadata={"source": "diagnostic"},
    )

    print("\n--- Streaming chunks received ---")
    chunk_types = set()
    text_parts: list[str] = []
    tool_calls_seen: list[str] = []
    tool_results_seen: list[str] = []
    finish_reason = "unknown"

    try:
        for chunk in loop.run_turn_stream(chat_input):
            chunk_types.add(chunk.kind)
            if chunk.kind == "text_delta":
                t = chunk.text_delta or ""
                text_parts.append(t)
                # Print tool results specially
                if t.startswith("\n[Tool `"):
                    tool_results_seen.append(t[:150])
                else:
                    pass  # text is printed by the display layer
            elif chunk.kind == "tool_call_delta":
                tool_calls_seen.append(f"{chunk.tool_name}({str(chunk.tool_arguments_delta or '')[:80]})")
            elif chunk.kind == "done":
                finish_reason = chunk.finish_reason or "stop"
    except Exception as exc:
        print(f"  ERROR in run_turn_stream: {exc}")
        import traceback
        traceback.print_exc()
        return

    full_text = "".join(text_parts)
    print(f"\n--- Summary ---")
    print(f"  Chunk types received: {sorted(chunk_types)}")
    print(f"  Tool calls: {len(tool_calls_seen)}")
    for tc in tool_calls_seen:
        print(f"    - {tc}")
    print(f"  Tool results: {len(tool_results_seen)}")
    for tr in tool_results_seen:
        print(f"    - {tr}")
    print(f"  Finish reason: {finish_reason}")
    print(f"  Collected text ({len(full_text)} chars):")
    # Show first 500 chars of non-tool-result text
    text_only = full_text
    import re
    text_only = re.sub(r'\n?\[Tool `[^`]+`:.*?\]', '', text_only, flags=re.DOTALL)
    print(f"    {text_only[:500]}")


if __name__ == "__main__":
    test_query("列出当前目录的文件结构", "list directory")
    print("\n\n")
    test_query("搜索 Python web framework 的最新信息", "web search")
