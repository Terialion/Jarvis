"""Tests for s17c: Semantic context reuse via Jaccard word-overlap similarity."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from src.jarvis.agent.loop import AgentLoop


class TestJaccardSimilarity:
    def test_identical(self):
        assert AgentLoop._jaccard_similarity("hello world", "hello world") == pytest.approx(1.0)

    def test_partial_overlap(self):
        sim = AgentLoop._jaccard_similarity("hello world foo", "hello world bar")
        assert sim == pytest.approx(0.5)  # {hello, world} / {hello, world, foo, bar}

    def test_no_overlap(self):
        assert AgentLoop._jaccard_similarity("abc xyz", "def uvw") == 0.0

    def test_empty(self):
        assert AgentLoop._jaccard_similarity("", "hello") == 0.0
        assert AgentLoop._jaccard_similarity("hello", "") == 0.0

    def test_short_words_filtered(self):
        """Words shorter than 3 chars are filtered out."""
        sim = AgentLoop._jaccard_similarity("a b c hello", "a b hello world")
        assert sim == pytest.approx(0.5)  # {hello} / {hello, world}

    def test_related_texts(self):
        """Semantically related texts should have measurable overlap."""
        sim = AgentLoop._jaccard_similarity(
            "python code editor agent tools loop context",
            "python agent loop tool execution context"
        )
        assert sim > 0.3


class TestContextReuseDetection:
    def test_keyword_marker_triggers_fast_path(self):
        """Explicit keywords like 刚才 should trigger context reuse immediately."""
        loop = AgentLoop.__new__(AgentLoop)

        mock_ctx = MagicMock()
        mock_ctx.retrieve_skill_observation.return_value = None
        mock_ctx.retrieve_research_observation.return_value = None
        loop.context_store = mock_ctx

        result = loop._detect_context_reuse_signals("刚才那个文件在哪里", "s1")
        assert result is None  # both retrievals return None
        mock_ctx.retrieve_skill_observation.assert_called_once()
        mock_ctx.retrieve_research_observation.assert_called_once()

    def test_keyword_marker_with_data(self):
        """Keyword match + existing observations returns signals."""
        loop = AgentLoop.__new__(AgentLoop)

        mock_ctx = MagicMock()
        mock_ctx.retrieve_skill_observation.return_value.to_dict.return_value = {
            "skill_name": "scan", "summary": "scanned files"
        }
        mock_ctx.retrieve_research_observation.return_value = None
        loop.context_store = mock_ctx

        result = loop._detect_context_reuse_signals("based on the previous result", "s2")
        assert result is not None
        assert result["skill_observation"]["skill_name"] == "scan"

    def test_semantic_fallback_no_keywords(self):
        """Without keywords, Jaccard overlap should still detect related context."""
        loop = AgentLoop.__new__(AgentLoop)

        mock_ctx = MagicMock()
        mock_ctx.retrieve_recent_context.return_value = {
            "skill_observations": [
                {"skill_name": "repo_overview", "summary": "python agent loop tool execution context project"},
            ],
            "research_observations": [],
        }
        loop.context_store = mock_ctx

        result = loop._detect_context_reuse_signals(
            "what tool execution context does this agent use",
            "s3"
        )
        assert result is not None
        assert "skill_observation" in result
        assert result["skill_observation"]["skill_name"] == "repo_overview"

    def test_semantic_fallback_unrelated(self):
        """Unrelated text should not trigger context reuse."""
        loop = AgentLoop.__new__(AgentLoop)

        mock_ctx = MagicMock()
        mock_ctx.retrieve_recent_context.return_value = {
            "skill_observations": [
                {"skill_name": "docker", "summary": "manage docker containers images"},
            ],
            "research_observations": [
                {"query": "weather", "answer_summary": "sunny today"},
            ],
        }
        loop.context_store = mock_ctx

        result = loop._detect_context_reuse_signals(
            "how do write python script for file processing",
            "s4"
        )
        assert result is None

    def test_semantic_fallback_handles_empty_observations(self):
        """Empty recent context should not crash."""
        loop = AgentLoop.__new__(AgentLoop)

        mock_ctx = MagicMock()
        mock_ctx.retrieve_recent_context.return_value = {
            "skill_observations": [],
            "research_observations": [],
        }
        loop.context_store = mock_ctx

        result = loop._detect_context_reuse_signals("some text about code", "s5")
        assert result is None
