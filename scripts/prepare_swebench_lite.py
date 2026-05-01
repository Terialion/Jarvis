"""Prepare SWE-bench Lite fixtures and environment checks."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def write_environment_check() -> None:
    path = ROOT / "temp" / "external_benchmarks" / "swebench_lite" / "environment_check.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "jarvis.swebench_lite.environment.v1",
        "docker_available": False,
        "dataset": {"name": "swebench_lite", "tasks_loaded": 0},
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def prepare_fixtures() -> None:
    d = ROOT / "temp" / "external_benchmarks" / "swebench_lite"
    d.mkdir(parents=True, exist_ok=True)
    # Write empty predictions placeholder
    (d / "predictions.jsonl").write_text("", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--prepare-fixtures", action="store_true")
    args = parser.parse_args()

    if args.check_only:
        write_environment_check()
    elif args.prepare_fixtures:
        prepare_fixtures()
    else:
        print("No action specified. Use --check-only or --prepare-fixtures.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
