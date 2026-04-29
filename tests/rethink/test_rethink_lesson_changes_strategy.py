from jarvis.core.rethink.evaluator import evaluate_rethink


def test_rethink_evaluator_returns_strategy_adjustment():
    result = evaluate_rethink({"test_failed": True}, available_skills=["skill.repo_fix"])
    assert result.decision.should_rethink is True
    assert result.strategy_adjustment.strategy != ""

