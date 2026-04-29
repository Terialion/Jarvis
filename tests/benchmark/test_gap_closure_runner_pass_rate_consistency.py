import json
from pathlib import Path


def test_runner_pass_rate_consistency():
    report = json.loads(Path("d:/jarvis/temp/gap_closure/final_report.json").read_text(encoding="utf-8"))
    calc = str(report.get("pass_rate_calculation") or "")
    core = float(report.get("core_e2e_pass_rate") or 0.0)
    assert "/" in calc
    lhs = calc.split("*", 1)[0]
    passed, total = lhs.split("/", 1)
    expected = round((int(passed) / max(1, int(total))) * 100.0, 2)
    assert abs(expected - core) < 0.01
