from __future__ import annotations

from benchmarks.case_schema import BenchmarkCase


def test_benchmark_case_schema_roundtrip():
    case = BenchmarkCase(
        id="c1",
        suite="jarvis_core",
        category="chat",
        input="hello",
        expected_behavior={"must_call_tools": False},
    )
    data = case.to_dict()
    parsed = BenchmarkCase.from_dict(data)
    assert parsed.id == "c1"
    assert parsed.suite == "jarvis_core"


def test_benchmark_case_schema_supports_turns_and_setup():
    parsed = BenchmarkCase.from_dict(
        {
            "case_id": "ctx_001",
            "suite": "context_skill",
            "category": "multi_turn_context",
            "turns": [{"input": "first"}, {"input": "second"}],
            "setup": {"force_compaction": True},
            "expected": {"must_context_reuse": True},
        }
    )
    assert parsed.id == "ctx_001"
    assert parsed.turns == [{"input": "first"}, {"input": "second"}]
    assert parsed.setup["force_compaction"] is True
    assert parsed.expected_behavior["must_context_reuse"] is True

