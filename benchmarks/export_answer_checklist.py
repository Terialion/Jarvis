from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _sanitize_md_cell(value: Any, limit: int | None = None) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    text = _collapse_ws(text)
    text = text.replace("|", r"\|")
    if limit is not None and len(text) > limit:
        text = text[: limit - 3] + "..."
    return text


def _failed_checks(checks: dict[str, Any]) -> list[str]:
    return [k for k, v in checks.items() if not bool(v)]


def _load_case_map() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    root = Path("benchmarks/suites")
    if not root.exists():
        return out
    for cases in root.glob("*/cases.jsonl"):
        for line in cases.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            text = line.strip()
            if not text:
                continue
            try:
                obj = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and obj.get("id"):
                out[str(obj["id"])] = obj
    return out


def _model_calls_count(run_result: dict[str, Any]) -> int:
    return sum(
        1
        for evt in list(run_result.get("events") or [])
        if str((evt or {}).get("type") or "") == "model_call_started"
    )


def _extract_rows(payload: dict[str, Any], case_map: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for suite in payload.get("suites", []):
        suite_name = str(suite.get("suite") or "")
        suite_model_backend = str(suite.get("model_backend") or payload.get("model_backend") or "unknown")
        suite_model_provider = str(suite.get("model_provider") or payload.get("model_provider") or "unknown")
        suite_model_name = str(suite.get("model_name") or payload.get("model_name") or "unknown")

        for row in suite.get("results", []):
            checks = dict(row.get("checks") or {})
            failed = _failed_checks(checks)
            run_result = dict(row.get("run_result") or {})
            case_id = str(row.get("case_id") or "")
            case_def = case_map.get(case_id, {})
            expected_behavior = dict(case_def.get("expected_behavior") or {})
            input_text = str(
                case_def.get("input")
                or run_result.get("events", [{}])[0].get("payload", {}).get("text", "")
                or ""
            )
            final_answer = str(run_result.get("final_answer") or "")
            stop_reason = str(run_result.get("stop_reason") or "")
            output_type = str(run_result.get("output_type") or "answer")
            machine = dict((run_result.get("summary") or {}).get("machine") or {})
            risks = list(machine.get("risks") or [])
            tools_used = list(machine.get("tools_used") or [])

            rows.append(
                {
                    "case_id": case_id,
                    "suite": suite_name,
                    "passed": bool(row.get("passed")),
                    "failed_checks": failed,
                    "model_backend": suite_model_backend,
                    "model_provider": suite_model_provider,
                    "model_name": suite_model_name,
                    "model_calls": _model_calls_count(run_result),
                    "tool_calls_count": len(list(run_result.get("tool_calls") or [])),
                    "output_type": output_type,
                    "stop_reason": stop_reason,
                    "input": input_text,
                    "expected_behavior": expected_behavior,
                    "final_answer_excerpt": final_answer[:200],
                    "risks": risks,
                    "tools_used": tools_used,
                }
            )
    return rows


def _render_markdown(payload: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    lines.append("# Benchmark Answer Checklist")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- scope: {payload.get('scope')}")
    lines.append(f"- execution_mode: {payload.get('execution_mode')}")
    lines.append(f"- model_provider: {payload.get('model_provider')}")
    lines.append(f"- model_backend: {payload.get('model_backend')}")
    lines.append("")

    by_suite: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_suite.setdefault(str(row["suite"]), []).append(row)

    for suite_name, suite_rows in by_suite.items():
        lines.append(f"## Suite: {suite_name}")
        lines.append("")
        lines.append(
            "| case_id | passed | failed_checks | output_type | model_calls | tool_calls_count | stop_reason | final_answer_excerpt | risks |"
        )
        lines.append("|---|---|---|---|---:|---:|---|---|---|---|")
        for row in suite_rows:
            excerpt = str(row.get("final_answer_excerpt") or "").replace("\n", " ").replace("\t", " ").strip()
            lines.append(
                f"| `{_sanitize_md_cell(row['case_id'])}` | "
                f"`{_sanitize_md_cell(row['passed'])}` | "
                f"`{_sanitize_md_cell(', '.join(row['failed_checks']) if row['failed_checks'] else 'none')}` | "
                f"`{_sanitize_md_cell(row['output_type'])}` | "
                f"`{_sanitize_md_cell(row['model_calls'])}` | "
                f"`{_sanitize_md_cell(row['tool_calls_count'])}` | "
                f"`{_sanitize_md_cell(row['stop_reason'], 80)}` | "
                f"{_sanitize_md_cell(excerpt, 120)} | "
                f"{_sanitize_md_cell(', '.join(row['risks']) if row['risks'] else 'none', 120)} |"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    latest = Path("benchmarks/reports/latest.json")
    if not latest.exists():
        print("missing benchmarks/reports/latest.json")
        return 1

    payload = json.loads(latest.read_text(encoding="utf-8"))
    case_map = _load_case_map()
    rows = _extract_rows(payload, case_map)

    out_md = Path("temp/benchmark_answer_checklist.md")
    out_json = Path("temp/benchmark_answer_checklist.json")
    out_md.parent.mkdir(parents=True, exist_ok=True)

    out_md.write_text(_render_markdown(payload, rows), encoding="utf-8")
    out_json.write_text(json.dumps({"meta": payload, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out_md))
    print(str(out_json))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
