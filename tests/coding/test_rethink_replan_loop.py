from __future__ import annotations

from src.jarvis.core.coding_loop.replan import replan_from_rethink
from src.jarvis.core.coding_loop.rethink import rethink_after_failure
from src.jarvis.core.coding_loop.schema import CodingLoopState, Observation


def test_rethink_record_exists_on_test_failure() -> None:
    state = CodingLoopState(task_id="t1", workspace_root=".", user_goal="fix")
    state.round = 1
    state.current_plan = ["initial plan"]
    obs = Observation(round=1, type="test_result", ok=False, summary="test failed")
    record = rethink_after_failure(state, obs)
    assert record.trigger == "test_failed"
    assert record.revised_plan


def test_replan_from_rethink_uses_revised_plan() -> None:
    state = CodingLoopState(task_id="t2", workspace_root=".", user_goal="fix")
    state.round = 1
    state.current_plan = ["initial plan"]
    obs = Observation(round=1, type="test_result", ok=False, summary="test failed")
    record = rethink_after_failure(state, obs)
    new_plan = replan_from_rethink(state, record)
    assert new_plan == record.revised_plan
