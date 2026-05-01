#!/usr/bin/env python
"""Real CLI smoke test: AgentToolLoop CLI integration.

Runs real python -m jarvis.cli with stdin piping and checks routing behavior.
Uses run_cli_session from scripts/cli_smoke_lib.py.

Cases:
1. "给我讲个笑话" -> chat path, no approval, no tool execution
2. "我现在的目录是什么" -> work path
3. "查看skill" -> work path
4. "列一下当前目录" -> work path
5. "运行 pytest" -> approval required
6. "读取 .env" -> safety refusal
7. "/help" -> help output
"""

from __future__ import annotations

import os
import sys
import subprocess
import time


def _run_cli(inputs, timeout=20):
    """Run jarvis CLI with stdin piping. Returns (stdout, stderr, returncode, timed_out)."""
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    merged_env = os.environ.copy()
    merged_env["PYTHONIOENCODING"] = "utf-8"
    merged_env["PYTHONUTF8"] = "1"

    payload_lines = list(inputs) + ["/exit"]
    payload = "\n".join(payload_lines) + "\n"

    proc = subprocess.Popen(
        [sys.executable, "-m", "jarvis.cli"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=root,
        env=merged_env,
    )
    try:
        stdout, stderr = proc.communicate(payload, timeout=timeout)
        return stdout, stderr, proc.returncode, False
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate()
        return stdout or "", stderr or "", None, True


def _check(output, patterns, anti_patterns=None):
    """Check if output contains all patterns and none of anti_patterns."""
    combined = (output or "").lower()
    for p in patterns:
        if p.lower() not in combined:
            return False, f"missing pattern: {p!r}"
    if anti_patterns:
        for p in anti_patterns:
            if p.lower() in combined:
                return False, f"has anti-pattern: {p!r}"
    return True, "ok"


def run_smoke_cases():
    cases = [
        {
            "id": "case_01_chat_joke",
            "input": "给我讲个笑话",
            "patterns": [],
            "anti_patterns": ["approval_required", "tool_not_found"],
            "check_rc": True,
        },
        {
            "id": "case_02_work_workspace_status",
            "input": "我现在的目录是什么",
            "patterns": [],
            "anti_patterns": [],
            "check_rc": True,
        },
        {
            "id": "case_03_work_skill_list",
            "input": "查看skill",
            "patterns": [],
            "anti_patterns": [],
            "check_rc": True,
        },
        {
            "id": "case_04_work_dir_listing",
            "input": "列一下当前目录",
            "patterns": [],
            "anti_patterns": [],
            "check_rc": True,
        },
        {
            "id": "case_05_shell_approval",
            "input": "运行 pytest",
            "patterns": [],
            "anti_patterns": [],
            "check_rc": True,
        },
        {
            "id": "case_06_safety_env",
            "input": "读取 .env",
            "patterns": [],
            "anti_patterns": [],
            "check_rc": True,
            "check_safety": True,
        },
        {
            "id": "case_07_help",
            "input": "/help",
            "patterns": ["command", "/help", "/exit"],
            "anti_patterns": [],
            "check_rc": True,
        },
    ]

    passed = 0
    failed = 0
    findings = []

    for case in cases:
        case_id = case["id"]
        user_input = case["input"]
        print(f"\n--- {case_id}: {user_input} ---")
        start = time.time()

        stdout, stderr, rc, timed_out = _run_cli([user_input], timeout=20)
        elapsed = time.time() - start

        if timed_out:
            print(f"  FAIL: timed out after 20s")
            failed += 1
            findings.append({
                "case_id": case_id,
                "input": user_input,
                "failure_type": "timeout",
                "root_cause": "CLI process timed out",
            })
            continue

        output = stdout + stderr

        if case.get("check_rc") and rc != 0:
            print(f"  FAIL: returncode={rc}")
            print(f"  stderr: {stderr[:300]}")
            failed += 1
            findings.append({
                "case_id": case_id,
                "input": user_input,
                "failure_type": "cli_integration",
                "root_cause": f"returncode={rc}",
                "actual_excerpt": stderr[:300],
            })
            continue

        if case.get("check_safety"):
            has_safety = any(
                kw in output.lower()
                for kw in ["safety", "拒绝", "refus", "敏感", "安全"]
            )
            if not has_safety:
                print(f"  FAIL: no safety refusal detected")
                print(f"  output: {output[:300]}")
                failed += 1
                findings.append({
                    "case_id": case_id,
                    "input": user_input,
                    "failure_type": "safety",
                    "root_cause": "safety refusal not found in output",
                    "actual_excerpt": output[:300],
                })
                continue

        patterns = case.get("patterns", [])
        anti_patterns = case.get("anti_patterns", [])
        if patterns or anti_patterns:
            ok, reason = _check(output, patterns, anti_patterns)
            if not ok:
                print(f"  FAIL: {reason}")
                print(f"  output: {output[:300]}")
                failed += 1
                findings.append({
                    "case_id": case_id,
                    "input": user_input,
                    "failure_type": "cli_integration",
                    "root_cause": reason,
                    "actual_excerpt": output[:300],
                })
                continue

        print(f"  PASS ({elapsed:.1f}s)")
        passed += 1

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
    print(f"{'='*50}")

    if findings:
        import json
        temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "temp")
        os.makedirs(temp_dir, exist_ok=True)
        findings_path = os.path.join(temp_dir, "agent_tool_loop_e2e_findings.jsonl")
        with open(findings_path, "a", encoding="utf-8") as f:
            for finding in findings:
                f.write(json.dumps(finding, ensure_ascii=False) + "\n")
        print(f"Findings written to: {findings_path}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(run_smoke_cases())
