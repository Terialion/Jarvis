"""Test that JSON tool_plan fragments are cleaned from thinking display text.

Reproduces the actual bug: when Qwen streams tool_plan_json inside
reasoning_content, the JSON is split across multiple reasoning_delta
chunks.  Per-chunk _strip_artifacts fails on partial JSON, so fragments
like ``]}}`` and ``, {"tool_name": ...}`` leak into the display.
"""

from __future__ import annotations

from src.jarvis.cli_ui.tui_utils import strip_artifacts


def _clean_thinking_text(thinking_blocks: list[str]) -> str:
    """Simulate post-stream thinking cleanup.

    Joins all accumulated blocks and runs strip_artifacts once on the
    complete text — this is the fix for per-chunk artifact leakage.
    """
    joined = "".join(thinking_blocks)
    return strip_artifacts(joined).strip()


def test_complete_tool_plan_json_cleaned():
    """A complete tool_plan_json in a single chunk is removed."""
    blocks = [
        '{"tool_plan_json": {"thought": "search", "tool_calls": ['
        '{"tool_name": "web.search", "arguments": {"query": "test"}}]}}'
    ]
    result = _clean_thinking_text(blocks)
    assert "tool_plan_json" not in result
    assert "web.search" not in result


def test_split_json_tail_fragment_cleaned():
    """JSON tail fragment like ``]}}`` arriving alone is cleaned."""
    blocks = [
        # Chunk 1: opening + first tool
        '{"tool_plan_json": {"thought": "do X", "tool_calls": ['
        '{"tool_name": "repo_reader.read_file", "arguments": {"path": "a.py"}}',
        # Chunk 2: more tools
        ', {"tool_name": "repo_reader.glob", "arguments": {"pattern": "**/*"}}',
        # Chunk 3: closing (the problematic fragment)
        "]}}",
    ]
    result = _clean_thinking_text(blocks)
    assert "]}}" not in result, f"Found trailing ]}} in: {result!r}"
    assert "tool_plan_json" not in result


def test_split_json_opening_fragment_cleaned():
    """JSON fragments across chunks cleaned when joined with wrapper."""
    blocks = [
        # Chunk 1: opening wrapper with tool_plan_json key
        '{"tool_plan_json": {"thought": "list src dir", "tool_calls": [',
        # Chunk 2: tool object with nested arguments
        '{"tool_name": "repo_reader.list_tree", "arguments": {"max_depth": 3, "path": "src"}}',
        # Chunk 3: closing
        "]}}",
        # Surrounding natural language
        "Now let me look at the results.",
    ]
    result = _clean_thinking_text(blocks)
    assert 'tool_name' not in result, f"Found tool_name in: {result!r}"
    assert "repo_reader.list_tree" not in result
    assert "Now let me look at the results." in result


def test_reasoning_text_surrounding_json_preserved():
    """Natural language surrounding tool_plan_json is preserved."""
    blocks = [
        "I need to compare two directories.",
        '{"tool_plan_json": {"thought": "list both", "tool_calls": ['
        '{"tool_name": "repo_reader.list_tree", "arguments": {"path": "src"}}]}}',
        "Now I have the structure, let me check specific files.",
    ]
    result = _clean_thinking_text(blocks)
    assert "I need to compare two directories." in result
    assert "tool_plan_json" not in result
    assert "tool_name" not in result


def test_empty_thinking_blocks():
    """Empty or whitespace-only blocks produce empty result."""
    assert _clean_thinking_text([]) == ""
    assert _clean_thinking_text(["", "   "]) == ""


def test_no_json_at_all_passthrough():
    """Plain thinking text without any JSON passes through unchanged."""
    blocks = [
        "Let me analyze the project structure.",
        "I see there are 12 files total.",
    ]
    result = _clean_thinking_text(blocks)
    assert "Let me analyze the project structure." in result
    assert "12 files total" in result


def test_xml_tool_call_cleaned():
    """XML <tool_call> blocks are removed."""
    blocks = [
        "I will use",
        "<tool_call><function=bash><parameter=command>mkdir -p test</parameter></function></tool_call>",
        "to create a directory.",
    ]
    result = _clean_thinking_text(blocks)
    assert "tool_call" not in result
    assert "function" not in result
    assert "mkdir" not in result
    assert "I will use" in result
    assert "to create a directory." in result


def test_split_xml_across_chunks_cleaned():
    """XML <tool_call> split across chunks is removed when joined."""
    blocks = [
        "Let me run: <tool_call><func",
        'tion=bash><parameter=command>echo hi</parameter></function></tool_call>',
    ]
    result = _clean_thinking_text(blocks)
    assert "tool_call" not in result, f"Found tool_call in: {result!r}"
    assert "function" not in result
    assert "echo hi" not in result


def test_keyword_thinking_blocks_only_fragment():
    """JSON fragments wrapped in markdown code fences are cleaned."""
    blocks = [
        '```json\n{"tool_plan_json": {"thought": "list", "tool_calls": [',
        '{"tool_name": "repo_reader_list_tree", "arguments": {"max_depth": 3, "path": "src"}}',
        ']}}\n```',
    ]
    result = _clean_thinking_text(blocks)
    assert "tool_plan_json" not in result
    assert "tool_name" not in result


def test_mixed_content_and_json():
    """Mixed natural language + partial JSON fragments (the real Qwen output pattern)."""
    blocks = [
        '我来查看一下项目结构，对比',
        '`jarvis` 和 `learn-claude-code`',
        '两个目录的内容。\n',
        '{"tool_plan_json": {"thought": "compare dirs", "tool_calls": [',
        ', {"tool_name": "repo_reader_list_tree", "arguments": {"max_depth": 3, "path": "learn-claude-code"}}',
        ']}}\n',
        '现在让我更详细地查看',
    ]
    result = _clean_thinking_text(blocks)
    assert "我来查看一下项目结构" in result
    assert "jarvis" in result
    assert "learn-claude-code" in result
    assert "现在让我更详细地查看" in result
    # JSON fragments must be gone
    assert 'tool_name' not in result, f"tool_name leaked: {result!r}"
    assert 'tool_plan_json' not in result
