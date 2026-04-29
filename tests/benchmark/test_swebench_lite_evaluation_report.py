import json
import subprocess
from pathlib import Path


ROOT = Path("d:/jarvis")
PY = ROOT / ".venv/Scripts/python.exe"


def test_evaluation_report_contains_failure_breakdown():
    subprocess.run([str(PY), "scripts/prepare_swebench_lite.py", "--prepare-fixtures"], cwd=str(ROOT), check=True)
    subprocess.run([str(PY), "scripts/run_swebench_lite_smoke.py", "--max-tasks", "1", "--dry-run"], cwd=str(ROOT), check=True)
    report = json.loads((ROOT / "temp/external_benchmarks/swebench_lite/smoke_report.json").read_text(encoding="utf-8"))
    summary = report.get("summary") or {}
    for key in ["environment_failures", "adapter_failures", "agent_failures", "benchmark_harness_failures", "skipped"]:
        assert key in summary

