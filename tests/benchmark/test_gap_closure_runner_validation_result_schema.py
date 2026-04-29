import json
from pathlib import Path


def test_runner_validation_result_schema():
    report = json.loads(Path("d:/jarvis/temp/gap_closure/final_report.json").read_text(encoding="utf-8"))
    assert "validation_commands" in report
    assert "validation_results" in report
    assert "failed_commands" in report
    assert "skipped_commands" in report
    assert "pass_rate_calculation" in report
    for item in report.get("validation_results", []):
        assert "command" in item
        assert "ok" in item
        assert "validation_status" in item
