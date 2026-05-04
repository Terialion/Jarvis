# Benchmark v0.1

## Objective

Benchmark v0.1 validates the real `AgentLoop.run_turn()` execution chain and reports behavioral gaps.

## Structure

- `benchmarks/case_schema.py`
- `benchmarks/run_benchmark.py`
- `benchmarks/evaluators/*.py`
- `benchmarks/suites/jarvis_core/cases.jsonl` (30)
- `benchmarks/suites/coding/cases.jsonl` (20)
- `benchmarks/suites/terminal/cases.jsonl` (10)
- `benchmarks/suites/web_research/cases.jsonl` (10)

## Required Binding

Runner imports:

- `from src.jarvis.agent.loop import AgentLoop`
- `from src.jarvis.agent.types import ChatInput`

No direct use of legacy `HeavyReActRuntime` in benchmark execution.

## Evaluation Checks

- `final_answer_exists`
- `summary_exists`
- `tool_call_schema_valid`
- `must_call_tools`
- `no_forbidden_tool`
- `must_include`
- `must_not_modify_files`
- `test_passed`
- `stop_reason_valid`
- `event_timeline_valid`

## Reports

- `benchmarks/reports/latest.json`
- `benchmarks/reports/latest.md`
- `benchmarks/reports/runs/<timestamp>_<suite>.json`

