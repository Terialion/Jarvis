from src.jarvis.core.recommendations import recommend_next_actions


def test_recommendation_after_repo_inspection() -> None:
    actions = recommend_next_actions({"current_stage": "repo_inspection"})
    assert any("coding smoke" in item.reason.lower() for item in actions)


def test_recommendation_after_coding_done() -> None:
    actions = recommend_next_actions({"stop_reason": "done"})
    assert actions[0].priority == "high"
    assert "Context" in actions[0].label


def test_recommendation_after_max_rounds() -> None:
    actions = recommend_next_actions({"stop_reason": "max_rounds"})
    assert "evidence" in actions[0].label.lower()

