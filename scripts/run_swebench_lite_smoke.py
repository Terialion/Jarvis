"""Run SWE-bench Lite smoke test (dry-run mode)."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-tasks", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    d = ROOT / "temp" / "external_benchmarks" / "swebench_lite"
    d.mkdir(parents=True, exist_ok=True)

    report = {
        "readiness": "dry_run_ready",
        "summary": {
            "harness_evaluated": 0,
            "environment_failures": 0,
            "adapter_failures": 0,
            "agent_failures": 0,
            "benchmark_harness_failures": 0,
            "skipped": args.max_tasks,
        },
        "tasks": [],
    }
    report_path = d / "smoke_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    pred_path = d / "predictions.jsonl"
    pred_path.write_text("", encoding="utf-8")


if __name__ == "__main__":
    main()
