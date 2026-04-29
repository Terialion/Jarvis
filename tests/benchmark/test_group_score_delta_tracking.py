import json
from pathlib import Path


def test_final_report_contains_score_delta_fields():
    path = Path("d:/jarvis/temp/gap_closure/final_report.json")
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert "score_delta" in payload
    assert "weighted_average_score" in payload

