from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.jarvis.core.coding_loop.orchestrator import run_coding_loop


def _prepare_fixture(workspace_root: Path) -> None:
    fixture_dir = workspace_root / "examples" / "coding_fixture"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    (fixture_dir / "greeting.py").write_text(
        'def greeting(name: str) -> str:\n'
        '    return f"Hello, {name}"\n',
        encoding="utf-8",
    )
    tests_dir = fixture_dir / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "test_greeting.py").write_text(
        "from examples.coding_fixture.greeting import greeting\n\n\n"
        "def test_greeting():\n"
        '    assert greeting("Jarvis") == "Hello, Jarvis!"\n',
        encoding="utf-8",
    )
    (workspace_root / "examples" / "__init__.py").write_text("", encoding="utf-8")
    (fixture_dir / "__init__.py").write_text("", encoding="utf-8")
    (tests_dir / "__init__.py").write_text("", encoding="utf-8")
    (workspace_root / "JARVIS.md").write_text(
        "# JARVIS.md\n\nUse scoped tests and report stop_reason.\n",
        encoding="utf-8",
    )


def _run_case(workspace_root: Path, name: str, force_first_failure: bool) -> dict:
    return run_coding_loop(
        "Fix greeting bug and run scoped tests.",
        workspace_root,
        max_rounds=3,
        auto_approve=True,
        force_first_failure=force_first_failure,
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="jarvis_coding_smoke_") as td:
        workspace = Path(td)
        _prepare_fixture(workspace)

        first_try = _run_case(workspace, "success_first_try", force_first_failure=False)

        _prepare_fixture(workspace)
        rethink_case = _run_case(workspace, "rethink_path", force_first_failure=True)

        print("Coding smoke complete.\n")
        print("Case: success_first_try")
        print(f"Rounds: {first_try['rounds']}")
        print(f"Stop reason: {first_try['stop_reason']}")
        print(f"Patch applied: {'yes' if first_try['diffs'] else 'no'}")
        print(f"Scoped tests: {'passed' if first_try['test_results'] and first_try['test_results'][-1]['passed'] else 'failed'}")
        print(f"Evidence: {first_try['trace_path']}\n")
        print(f"JARVIS.md loaded: {'yes' if any(s.get('scope') == 'project' for s in first_try.get('instruction_sources', [])) else 'no'}\n")

        print("Case: rethink_path")
        print(f"Rounds: {rethink_case['rounds']}")
        first_stop = "test_failed" if rethink_case["rethink_records"] else "none"
        print(f"First stop reason: {first_stop}")
        print(f"Rethink: {'yes' if rethink_case['rethink_records'] else 'no'}")
        print(f"Replan: {'yes' if rethink_case['rethink_records'] else 'no'}")
        print(f"Final stop reason: {rethink_case['stop_reason']}")

        cli = subprocess.run(
            [sys.executable, "-m", "jarvis.cli"],
            input="fix this bug and run tests\n/exit\n",
            text=True,
            capture_output=True,
            cwd=str(ROOT),
            timeout=60,
            encoding="utf-8",
            errors="replace",
        )
        cli_uses_orchestrator = "Coding loop complete." in (cli.stdout or "") and "Stop reason" in (cli.stdout or "")
        print(f"CLI coding path uses orchestrator: {'yes' if cli_uses_orchestrator else 'no'}")

        ok = (
            first_try["stop_reason"] == "done"
            and rethink_case["rounds"] >= 2
            and rethink_case["stop_reason"] in {"done", "max_rounds"}
            and bool(rethink_case["rethink_records"])
            and any(s.get("scope") == "project" for s in first_try.get("instruction_sources", []))
            and cli_uses_orchestrator
        )
        if not ok:
            print("\nFailure details:")
            print(json.dumps({"success_first_try": first_try, "rethink_path": rethink_case}, ensure_ascii=False, indent=2))
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
