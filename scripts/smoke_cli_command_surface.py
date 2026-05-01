#!/usr/bin/env python
"""Real CLI command surface smoke.

Starts `python -m jarvis.cli` and feeds slash commands through stdin.
"""

from __future__ import annotations

from pathlib import Path

from cli_smoke_lib import classify_output, discover_preferred_skills, discover_slash_commands, ensure_temp, make_finding, run_cli_session, write_jsonl


def _forms(command: str) -> list[tuple[str, str]]:
    if command == "/exit":
        return [("no_args", "/exit")]
    arg = "sample-arg"
    examples = {
        "/skill": "code-generator 写一个 hello.py",
        "/skills": "search python",
        "/task": "115",
        "/model": "gpt-5.5-thinking",
        "/test": "tests/routing",
        "/review": "tests/routing",
        "/approve": "last",
        "/reject": "last",
        "/permissions": "read-only",
        "/sandbox-add-read-dir": "D:/tmp",
        "/compact": "now",
        "/resume": "last",
    }
    arg = examples.get(command, arg)
    return [("no_args", command), ("help_form", f"{command} --help"), ("arg_form", f"{command} {arg}")]


def main() -> int:
    temp = ensure_temp()
    findings_path = temp / "command_surface_findings.jsonl"
    report_path = temp / "command_surface_report.md"
    rows = []
    findings = []

    commands = discover_slash_commands()
    for skill in discover_preferred_skills(8):
        commands.append({"command": f"/{skill}", "source": "/skills output", "spec": None})
    for extra in ["/unknown", "/skil", "/skillz", "/Users/a/file.py", "/home/alice/repo/README.md", "/etc/hosts", "/tmp/test.py"]:
        commands.append({"command": extra, "source": "bench extra", "spec": None})

    seen = set()
    unique = []
    for item in commands:
        if item["command"] in seen:
            continue
        seen.add(item["command"])
        unique.append(item)

    for item in unique:
        command = item["command"]
        result_cells = {}
        combined = ""
        for form_name, text in _forms(command):
            lines = [text] if text == "/exit" else [text, "/exit"]
            try:
                run = run_cli_session(lines, timeout=60)
                output = run.output
                combined += "\n" + output
                ok = run.returncode == 0 and "Traceback" not in output
                result_cells[form_name] = "pass" if ok else "fail"
                if not ok:
                    findings.append(make_finding(f"command_surface_{command}_{form_name}", text, "slash_command", "returncode 0 without crash", output, "crash"))
            except Exception as exc:
                result_cells[form_name] = "fail"
                findings.append(make_finding(f"command_surface_{command}_{form_name}", text, "slash_command", "no timeout", type(exc).__name__, "timeout"))
        flags = classify_output(combined)
        status = "pass" if all(v == "pass" for v in result_cells.values()) else "fail"
        rows.append(
            {
                "command": command,
                "source": item["source"],
                "no_args": result_cells.get("no_args", "n/a"),
                "help_form": result_cells.get("help_form", "n/a"),
                "arg_form": result_cells.get("arg_form", "n/a"),
                "entered_llm": str(flags["entered_llm"]).lower(),
                "entered_task_flow": str(flags["entered_task_flow"]).lower(),
                "status": status,
                "notes": "approval/refusal observed" if flags["approval"] or flags["refusal"] else "",
            }
        )

    lines = [
        "# Jarvis CLI Command Surface Report",
        "",
        f"Discovered commands: {len(unique)}",
        "",
        "command | source | no_args | help_form | arg_form | entered_llm | entered_task_flow | status | notes",
        "--- | --- | --- | --- | --- | --- | --- | --- | ---",
    ]
    for row in rows:
        lines.append(
            f"{row['command']} | {row['source']} | {row['no_args']} | {row['help_form']} | {row['arg_form']} | {row['entered_llm']} | {row['entered_task_flow']} | {row['status']} | {row['notes']}"
        )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_jsonl(findings_path, findings)
    print(f"command_surface_report={report_path}")
    print(f"command_surface_findings={findings_path}")
    print(f"commands_tested={len(unique)}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
