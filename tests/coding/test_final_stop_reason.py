from src.jarvis.core.coding_loop.review import build_final_review


def test_final_review_contains_stop_reason() -> None:
    review = build_final_review({"status": "success", "stop_reason": "done", "rounds": 1, "test_results": [{"passed": True}], "changed_files": ["x.py"]})
    assert review["stop_reason"] == "done"
    assert review["test_status"] == "passed"
    assert review["changed_files"] == ["x.py"]

