"""
CLI batch input test harness for Jarvis.

Provides `run_cli_session` which starts `python -m jarvis.cli`,
feeds inputs via stdin, appends `/exit`, captures output,
and enforces timeout with proper cleanup.
"""

from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

_DEFAULT_JARVIS_ENTRY = "jarvis.cli:main"  # adjust if your entry point differs
_TIMEOUT_DEFAULT = 30.0  # seconds

# Shared root directory (workspace root)
ROOT = Path(__file__).resolve().parents[1]

# Temp directory for smoke artifacts
def ensure_temp() -> Path:
    p = ROOT / "temp" / "cli_fuzz"
    p.mkdir(parents=True, exist_ok=True)
    return p


def make_finding(case_id: str, input_text: str, suite: str, expected: str,
                 actual: str, failure_type: str) -> dict:
    return {
        "case_id": case_id,
        "input": input_text[:500],
        "expected": expected,
        "actual_excerpt": actual[:2000],
        "failure_type": failure_type,
    }


def write_jsonl(path: Path, records: list) -> None:
    import json
    with open(path, "a", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


@dataclass
class CliRunResult:
    inputs: List[str]
    stdout: str
    stderr: str
    returncode: Optional[int]
    timed_out: bool
    output_by_input: dict[str, str] = field(default_factory=dict)
    error: Optional[str] = None


def _build_jarvis_cli_cmd(python_exe: str) -> List[str]:
    """Build the command to start jarvis CLI."""
    return [python_exe, "-m", "jarvis.cli"]


def _append_exit(inputs: List[str]) -> List[str]:
    """Ensure /exit is the last effective input."""
    inputs = list(inputs)
    if not inputs or inputs[-1].strip().lower() != "/exit":
        inputs.append("/exit")
    return inputs


def _split_output_by_input(stdout: str, inputs: List[str]) -> dict[str, str]:
    """
    A best-effort attempt to attribute stdout segments to inputs.
    This is heuristic and may need adjustment for your CLI's actual prompt format.
    """
    mapping: dict[str, str] = {}
    if not stdout:
        return mapping
    # Very naive split: assume each input line appears in stdout.
    # Override this with a more robust parser if needed.
    remaining = stdout
    for inp in inputs:
        if inp.strip() in remaining:
            idx = remaining.index(inp.strip())
            # take text after the input until next input or end
            next_idx = len(remaining)
            for other in inputs:
                if other == inp:
                    continue
                oidx = remaining.index(other.strip()) if other.strip() in remaining else None
                if oidx is not None and oidx > idx and oidx < next_idx:
                    next_idx = oidx
            mapping[inp] = remaining[idx + len(inp.strip()):next_idx].strip()
            remaining = remaining[next_idx:]
        else:
            mapping[inp] = ""
    return mapping


def run_cli_session(
    inputs: List[str],
    *,
    python_exe: Optional[str] = None,
    jarvis_root: Optional[str] = None,
    timeout: float = _TIMEOUT_DEFAULT,
    env: Optional[dict] = None,
) -> CliRunResult:
    """
    Start `python -m jarvis.cli`, feed inputs via stdin, collect outputs.

    Args:
        inputs: lines to feed to the REPL (does NOT need to include /exit).
        python_exe: path to the python executable to use.
        jarvis_root: if provided, used as cwd / env override.
        timeout: seconds before killing the subprocess.
        env: optional extra environment variables.

    Returns:
        CliRunResult with stdout/stderr, parsed output_by_input, and timing info.
    """
    python_exe = python_exe or sys.executable
    inputs = _append_exit(inputs)
    payload = "\n".join(inputs) + "\n"

    cmd = _build_jarvis_cli_cmd(python_exe)
    cwd = str(jarvis_root) if jarvis_root else None

    merged_env = dict(env or {})
    # Ensure PYTHONIOENCODING / PYTHONUTF8 are sane on Windows
    merged_env.setdefault("PYTHONIOENCODING", "utf-8")
    merged_env.setdefault("PYTHONUTF8", "1")

    proc = None
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=cwd,
            env=merged_env or None,
        )
        try:
            stdout, stderr = proc.communicate(payload, timeout=timeout)
            timed_out = False
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            timed_out = True

        output_by_input = _split_output_by_input(stdout, inputs)
        return CliRunResult(
            inputs=inputs,
            stdout=stdout or "",
            stderr=stderr or "",
            returncode=proc.returncode,
            timed_out=timed_out,
            output_by_input=output_by_input,
            error="TIMEOUT" if timed_out else None,
        )
    except Exception as exc:
        if proc is not None:
            try:
                proc.kill()
            except Exception:
                pass
        return CliRunResult(
            inputs=inputs,
            stdout="",
            stderr="",
            returncode=None,
            timed_out=False,
            error=f"FAILED to run CLI: {exc}",
        )
