from __future__ import annotations

from benchmarks import run_benchmark


def test_multi_turn_runner_reuses_same_session_and_context():
    case = next(case for case in run_benchmark._load_cases("context_skill") if case.id == "context_skill_ctx_001")
    run_result = run_benchmark._run_case(case, model_mode="fake")
    assert run_result["turn_count"] == 2
    assert len(set(run_result["all_session_ids"])) == 1
    assert run_result["summary"]["machine"]["context_reuse"] is True
    assert "README.md" in run_result["final_answer"]
