import json
import subprocess
from pathlib import Path


ROOT = Path("d:/jarvis")
PY = ROOT / ".venv/Scripts/python.exe"


def test_swebench_lite_dry_run_outputs():
    subprocess.run([str(PY), "scripts/prepare_swebench_lite.py", "--prepare-fixtures"], cwd=str(ROOT), check=True)
    completed = subprocess.run(
        [str(PY), "scripts/run_swebench_lite_smoke.py", "--max-tasks", "1", "--dry-run"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    report_path = ROOT / "temp/external_benchmarks/swebench_lite/smoke_report.json"
    pred_path = ROOT / "temp/external_benchmarks/swebench_lite/predictions.jsonl"
    assert report_path.exists()
    assert pred_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["readiness"] == "dry_run_ready"
    assert report["summary"]["harness_evaluated"] == 0

