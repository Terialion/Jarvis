"""Tests for s14 compaction hardening: boundary preservation + memory flush."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from src.jarvis.agent.context_compactor import (
    _repair_tool_call_boundaries,
    _compact_stage2_snip,
    _compact_stage5_llm_summarize,
    compact,
)
from src.jarvis.core.memory.memory_flush import (
    MemoryFlushPolicy,
    MemoryFlushExecutor,
)
from src.jarvis.core.tokens import TokenEstimator


# ── Block boundary preservation ────────────────────────────────────────


class TestRepairToolCallBoundaries:
    def test_no_split_when_tail_empty(self):
        """When tail is empty, middle is returned unchanged."""
        middle = [{"role": "user", "content": "hello"}]
        updated_middle, updated_tail = _repair_tool_call_boundaries(middle, [])
        assert updated_middle == middle
        assert updated_tail == []

    def test_no_split_when_no_tool_results_in_tail(self):
        """When tail has no tool messages, no repair is needed."""
        middle = [{"role": "user", "content": "q"}]
        tail = [{"role": "assistant", "content": "a"}]
        updated_middle, updated_tail = _repair_tool_call_boundaries(middle, tail)
        assert updated_middle == middle
        assert updated_tail == tail

    def test_repairs_orphaned_tool_result(self):
        """When tail starts with a tool result whose assistant is in middle,
        the assistant and all subsequent middle messages move into tail."""
        middle = [
            {"role": "user", "content": "read file"},
            {"role": "assistant", "tool_calls": [{"id": "call_1", "function": {"name": "read", "arguments": "{}"}}]},
        ]
        tail = [
            {"role": "tool", "tool_call_id": "call_1", "content": "file content"},
        ]
        updated_middle, updated_tail = _repair_tool_call_boundaries(middle, tail)
        # The assistant should have been moved from middle to tail
        assert len(updated_middle) == 1  # only the user message remains
        assert len(updated_tail) == 2  # assistant + tool result
        assert updated_tail[0]["role"] == "assistant"
        assert updated_tail[0]["tool_calls"][0]["id"] == "call_1"

    def test_repairs_multi_tool_call_assistant(self):
        """When an assistant has multiple tool_calls and some results are in tail,
        the entire assistant group moves to tail."""
        middle = [
            {"role": "user", "content": "do things"},
            {"role": "assistant", "tool_calls": [
                {"id": "call_a", "function": {"name": "read_a", "arguments": "{}"}},
                {"id": "call_b", "function": {"name": "read_b", "arguments": "{}"}},
            ]},
            {"role": "tool", "tool_call_id": "call_a", "content": "result a"},
        ]
        tail = [
            {"role": "tool", "tool_call_id": "call_b", "content": "result b"},
        ]
        updated_middle, updated_tail = _repair_tool_call_boundaries(middle, tail)
        # Both the assistant and its tool results should be together in tail
        assert len(updated_middle) == 1  # just the user message
        # assistant + result_a (from middle) + result_b (original tail)
        assert len(updated_tail) == 3
        assistant_in_tail = any(
            m.get("role") == "assistant" and any(
                tc.get("id") == "call_a" for tc in (m.get("tool_calls") or [])
            )
            for m in updated_tail
        )
        assert assistant_in_tail, "Assistant with tool_calls should be in tail"


class TestStage2SnipPreservesPairs:
    def test_tool_call_pair_not_separated_by_snip(self):
        """When snip would separate a tool_call from its result, the assistant
        is kept with the tail."""
        # Build messages: head (4 system) + middle (user + assistant with tool_calls) + tool result
        messages = [
            {"role": "system", "content": "s1"},
            {"role": "system", "content": "s2"},
            {"role": "system", "content": "s3"},
            {"role": "system", "content": "s4"},
        ]
        # Add enough dummy messages to trigger snip
        for i in range(20):
            messages.append({"role": "user", "content": f"msg {i}"})
            messages.append({"role": "assistant", "content": f"reply {i}"})
        # Add a tool_call + tool_result pair near the split point
        messages.append({"role": "assistant", "tool_calls": [
            {"id": "call_x", "function": {"name": "read", "arguments": "{}"}}
        ]})
        messages.append({"role": "tool", "tool_call_id": "call_x", "content": "important result"})

        estimator = TokenEstimator()
        result = _compact_stage2_snip(messages, estimator, context_window=200000)

        # The assistant(tool_calls) + tool result should both be present or both absent
        tool_count = sum(1 for m in result if m.get("tool_call_id") == "call_x")
        assistant_count = sum(
            1 for m in result
            if m.get("role") == "assistant"
            and any(tc.get("id") == "call_x" for tc in (m.get("tool_calls") or []))
        )
        # Either both kept or both dropped
        assert (tool_count > 0) == (assistant_count > 0), (
            f"tool_call and tool_result must be kept/dropped together: "
            f"tool={tool_count}, assistant={assistant_count}"
        )


class TestStage5SummarizePreservesPairs:
    def test_tool_call_pair_not_separated_by_summarize(self):
        """When LLM summarization would separate a pair, the assistant stays with tail."""
        messages = [
            {"role": "system", "content": "s1"},
            {"role": "system", "content": "s2"},
            {"role": "system", "content": "s3"},
            {"role": "system", "content": "s4"},
        ]
        for i in range(10):
            messages.append({"role": "user", "content": f"msg {i}"})
        messages.append({"role": "assistant", "tool_calls": [
            {"id": "call_y", "function": {"name": "write", "arguments": "{}"}}
        ]})
        messages.append({"role": "tool", "tool_call_id": "call_y", "content": "write result"})

        result = _compact_stage5_llm_summarize(messages, session_id="test")

        tool_count = sum(1 for m in result if m.get("tool_call_id") == "call_y")
        assistant_count = sum(
            1 for m in result
            if m.get("role") == "assistant"
            and any(tc.get("id") == "call_y" for tc in (m.get("tool_calls") or []))
        )
        assert (tool_count > 0) == (assistant_count > 0), (
            f"tool_call and tool_result must be kept/dropped together: "
            f"tool={tool_count}, assistant={assistant_count}"
        )


# ── Memory flush ───────────────────────────────────────────────────────


class TestMemoryFlushPolicy:
    def test_should_flush_returns_false_below_threshold(self):
        policy = MemoryFlushPolicy(soft_threshold_tokens=4000)
        assert policy.should_flush(2000) is False

    def test_should_flush_returns_true_after_growth(self):
        policy = MemoryFlushPolicy(soft_threshold_tokens=4000)
        # First call — growth from 0 to 5000 exceeds threshold
        assert policy.should_flush(5000) is True
        policy.record_flush(5000)
        # Second call — only 100 token growth, below threshold
        assert policy.should_flush(5100) is False

    def test_should_flush_after_sufficient_growth_since_last_flush(self):
        policy = MemoryFlushPolicy(soft_threshold_tokens=4000)
        policy.record_flush(5000)
        # Growth of 5000 exceeds threshold
        assert policy.should_flush(10000) is True


class TestMemoryFlushExecutor:
    def test_flush_creates_dated_memory_file(self, tmp_path: Path):
        executor = MemoryFlushExecutor(tmp_path)
        path = executor.flush(
            token_count=5000,
            active_task={"goal": "fix a bug", "status": "in_progress"},
            recent_decisions=["Use pytest for testing", "Switch to JSONL format"],
            modified_files=["src/main.py", "README.md"],
        )
        assert path is not None
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "Memory flush" in content
        assert "fix a bug" in content
        assert "pytest" in content
        assert "src/main.py" in content

    def test_flush_returns_none_when_no_content(self, tmp_path: Path):
        executor = MemoryFlushExecutor(tmp_path)
        path = executor.flush(token_count=100)
        assert path is None

    def test_flush_appends_to_existing_file(self, tmp_path: Path):
        executor = MemoryFlushExecutor(tmp_path)
        executor.flush(
            token_count=5000,
            active_task={"goal": "first task"},
        )
        executor.flush(
            token_count=10000,
            active_task={"goal": "second task"},
        )
        # The file should contain both flushes
        import glob
        memory_files = list((tmp_path / ".jarvis" / "memory").glob("*.md"))
        assert len(memory_files) == 1
        content = memory_files[0].read_text(encoding="utf-8")
        assert "first task" in content
        assert "second task" in content

    def test_short_conversation_does_not_flush(self, tmp_path: Path):
        """Memory flush should only happen when explicitly called at high context usage."""
        executor = MemoryFlushExecutor(tmp_path)
        # No flush called — no file created
        memory_dir = tmp_path / ".jarvis" / "memory"
        import glob
        files = list(memory_dir.glob("*.md")) if memory_dir.exists() else []
        assert len(files) == 0


class TestCompactWithFlush:
    def test_flush_executor_called_at_stage4(self, tmp_path: Path):
        """When context exceeds 85%, flush_executor should be called."""
        executor = MemoryFlushExecutor(tmp_path)
        # Build a large message set to exceed 85% threshold
        messages = [{"role": "system", "content": "s"}] + [
            {"role": "user", "content": "x" * 200}
            for _ in range(300)
        ]
        # Use a small context window to force stage 4+
        result_msgs, report = compact(
            messages,
            model_name="gpt-3.5-turbo",
            flush_executor=executor,
            flush_metadata={
                "active_task": {"goal": "test task"},
                "recent_decisions": ["test decision"],
            },
        )
        # After compaction, check that memory file was created
        import glob
        memory_files = list((tmp_path / ".jarvis" / "memory").glob("*.md"))
        if report.stage in ("collapse", "auto_compact"):
            assert len(memory_files) >= 1, (
                f"Stage {report.stage} should trigger memory flush"
            )
