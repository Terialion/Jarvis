import json
from pathlib import Path


def test_final_report_round_pointer_guard():
    final_path = Path("d:/jarvis/temp/gap_closure/final_report.json")
    assert final_path.exists()
    payload = json.loads(final_path.read_text(encoding="utf-8"))
    rounds = int(payload.get("rounds_executed") or 0)
    if rounds > 0:
        assert Path(f"d:/jarvis/temp/gap_closure/round_{rounds}.json").exists()

