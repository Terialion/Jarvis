from __future__ import annotations

from src.jarvis.core.coding_loop.judge import judge_coding_success
from src.jarvis.core.coding_loop.schema import CodingLoopState, Observation


def test_judge_success_done() -> None:
    state = CodingLoopState(task_id="t1", workspace_root=".", user_goal="fix")
    state.round = 1
    state.observations.append(Observation(round=1, type="patch_result", ok=True, summary="patched"))
    state.test_results.append({"passed": True})
    decision = judge_coding_success(state)
    assert decision.decision == "success"
    assert decision.stop_reason == "done"


def test_judge_test_failed_replan() -> None:
    state = CodingLoopState(task_id="t2", workspace_root=".", user_goal="fix")
    state.round = 1
    state.observations.append(Observation(round=1, type="patch_result", ok=True, summary="patched"))
    state.test_results.append({"passed": False})
    decision = judge_coding_success(state)
    assert decision.decision == "replan"
    assert decision.stop_reason == "test_failed"


def test_judge_max_rounds() -> None:
    state = CodingLoopState(task_id="t3", workspace_root=".", user_goal="fix", max_rounds=2)
    state.round = 2
    decision = judge_coding_success(state)
    assert decision.decision == "max_rounds"
    assert decision.stop_reason == "max_rounds"
