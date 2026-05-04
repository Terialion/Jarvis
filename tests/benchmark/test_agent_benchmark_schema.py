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

