from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    repo_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(repo_root))

from benchmarks.case_schema import BenchmarkCase
from benchmarks.evaluators.behavioral import BehavioralEvaluator
from benchmarks.evaluators.coding import CodingEvaluator
from benchmarks.evaluators.terminal import TerminalEvaluator
from benchmarks.evaluators.web_research import WebResearchEvaluator
from src.jarvis.agent.loop import AgentLoop
from src.jarvis.agent.model import FakeModelClient, RuntimeModelClient
from src.jarvis.agent.types import ChatInput

REPORT_ROOT = Path("benchmarks/reports")
SUITES = ("jarvis_core", "coding", "terminal", "web_research")


def _load_cases(suite: str, max_cases: int | None = None) -> list[BenchmarkCase]:
    path = Path("benchmarks") / "suites" / suite / "cases.jsonl"
    if not path.exists():
        return []
    rows: list[BenchmarkCase] = []
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            rows.append(BenchmarkCase.from_dict(obj))
    if max_cases is not None and max_cases > 0:
        return rows[:max_cases]
    return rows


def _evaluator_for_suite(suite: str):
    if suite == "coding":
        return CodingEvaluator()
    if suite == "terminal":
        return TerminalEvaluator()
    if suite == "web_research":
        return WebResearchEvaluator()
    return BehavioralEvaluator()


def _run_case(agent: AgentLoop, case: BenchmarkCase) -> dict[str, Any]:
    chat_input = ChatInput(
        text=case.input,
        project_id=case.suite,
        cwd=case.workspace or ".",
        metadata={"benchmark_case_id": case.id},
    )
    result = agent.run_turn(chat_input).to_dict()
    return result


def _suite_pass_rate(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    passed = sum(1 for row in rows if bool(row.get("passed")))
    return passed / len(rows)


def _compute_suite_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute enhanced behavior metrics from run results.

    Computes:
    - output_type_distribution: count of each output_type
    - tool_calls_avg: average number of tool calls per case
    - duplicate_tool_call_rate: fraction of cases with at least one tool_call_deduped event
    - timeout_rate: fraction of cases with stop_reason=timeout
    - no_progress_rate: fraction of cases with stop_reason=no_progress
    - provider_error_rate: fraction of cases with output_type=error
    - secret_leak_count: cases where final_answer contains potential secret patterns
    """
    if not results:
        return {}

    output_types: dict[str, int] = {}
    tool_calls_totals: list[int] = []
    dedup_count = 0
    timeout_count = 0
    no_progress_count = 0
    error_count = 0
    secret_leak_count = 0

    secret_patterns = ("sk-", "api_key", "token=", "password=", "secret=", "-----begin")

    for row in results:
        run_result = dict(row.get("run_result") or {})
        ot = str(run_result.get("output_type") or "answer")
        output_types[ot] = output_types.get(ot, 0) + 1

        tool_calls = list(run_result.get("tool_calls") or [])
        tool_calls_totals.append(len(tool_calls))

        events = list(run_result.get("events") or [])
        has_dedup = any(str((e or {}).get("type") or "") == "tool_call_deduped" for e in events)
        if has_dedup:
            dedup_count += 1

        stop_reason = str(run_result.get("stop_reason") or "")
        if stop_reason == "timeout":
            timeout_count += 1
        elif stop_reason == "no_progress":
            no_progress_count += 1

        if ot == "error":
            error_count += 1

        final_answer = str(run_result.get("final_answer") or "")
        if any(pat in final_answer.lower() for pat in secret_patterns):
            secret_leak_count += 1

    n = len(results)
    return {
        "output_type_distribution": output_types,
        "tool_calls_avg": round(sum(tool_calls_totals) / n, 3) if n else 0.0,
        "duplicate_tool_call_rate": round(dedup_count / n, 3) if n else 0.0,
        "timeout_rate": round(timeout_count / n, 3) if n else 0.0,
        "no_progress_rate": round(no_progress_count / n, 3) if n else 0.0,
        "provider_error_rate": round(error_count / n, 3) if n else 0.0,
        "secret_leak_count": secret_leak_count,
    }


def _build_model_client(model_mode: str) -> tuple[Any | None, dict[str, str], str]:
    mode = (model_mode or "auto").strip().lower()
    if mode == "fake":
        return FakeModelClient(), {
            "model_backend": "fake",
            "model_provider": "fake",
            "model_name": "fake-agent-v0",
            "api_key_source": "none",
        }, "fake_model"
    runtime_client = RuntimeModelClient()
    info = runtime_client.backend_info()
    if mode == "real":
        return runtime_client, info, "real_llm"
    return runtime_client, info, "auto"


def run_suite(suite: str, max_cases: int | None = None, model_mode: str = "auto") -> dict[str, Any]:
    cases = _load_cases(suite, max_cases=max_cases)
    evaluator = _evaluator_for_suite(suite)
    model_client, model_info, execution_mode = _build_model_client(model_mode)
    # Keep approval/policy chain active but auto-approve in benchmark mode
    # so offline suites can exercise tool execution deterministically.
    agent = AgentLoop(
        project_root=".",
        permission_mode="workspace_write",
        auto_approve=True,
        model_client=model_client,
    )

    results: list[dict[str, Any]] = []
    for case in cases:
        run_result = _run_case(agent, case)
        eval_result = evaluator.evaluate(case, run_result)
        results.append(
            {
                "case_id": case.id,
                "suite": suite,
                "category": case.category,
                "passed": eval_result.passed,
                "score": eval_result.score(),
                "checks": eval_result.checks,
                "run_result": run_result,
            }
        )
    metrics = _compute_suite_metrics(results)
    return {
        "suite": suite,
        "total": len(results),
        "pass_rate": _suite_pass_rate(results),
        "execution_mode": execution_mode,
        "model_provider": model_info.get("model_provider", "unknown"),
        "model_name": model_info.get("model_name", "unknown"),
        "model_backend": model_info.get("model_backend", "unknown"),
        "api_key_source": model_info.get("api_key_source", "missing"),
        "results": results,
        "metrics": metrics,
    }


def _write_reports(payload: dict[str, Any]) -> None:
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    runs_dir = REPORT_ROOT / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    scope = str(payload.get("scope") or "all")

    latest_json = REPORT_ROOT / "latest.json"
    latest_md = REPORT_ROOT / "latest.md"
    run_json = runs_dir / f"{timestamp}_{scope}.json"

    latest_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    run_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    latest_md.write_text(_render_markdown(payload), encoding="utf-8")


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = ["# Benchmark Report", ""]
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- scope: {payload.get('scope')}")
    if payload.get("execution_mode"):
        lines.append(f"- execution_mode: {payload.get('execution_mode')}")
    if payload.get("model_provider"):
        lines.append(f"- model_provider: {payload.get('model_provider')}")
    if payload.get("model_name"):
        lines.append(f"- model_name: {payload.get('model_name')}")
    if payload.get("model_backend"):
        lines.append(f"- model_backend: {payload.get('model_backend')}")
    lines.append("")
    lines.append("| Suite | Cases | Pass Rate |")
    lines.append("|---|---:|---:|")
    for suite in payload.get("suites", []):
        lines.append(f"| {suite.get('suite')} | {suite.get('total')} | {suite.get('pass_rate', 0.0):.2%} |")
    lines.append("")
    lines.append("## Behavior Metrics")
    lines.append("")
    # Aggregate metrics across all suites
    total_cases = sum(s.get("total", 0) for s in payload.get("suites", []))
    if total_cases > 0:
        ot_dist: dict[str, int] = {}
        tool_calls_totals_sum = 0
        dedup_total = 0
        timeout_total = 0
        no_progress_total = 0
        error_total = 0
        secret_leak_total = 0
        for s in payload.get("suites", []):
            m = s.get("metrics", {}) or {}
            for k, v in m.get("output_type_distribution", {}).items():
                ot_dist[k] = ot_dist.get(k, 0) + v
            tool_calls_totals_sum += m.get("tool_calls_avg", 0) * s.get("total", 0)
            dedup_total += m.get("duplicate_tool_call_rate", 0) * s.get("total", 0)
            timeout_total += m.get("timeout_rate", 0) * s.get("total", 0)
            no_progress_total += m.get("no_progress_rate", 0) * s.get("total", 0)
            error_total += m.get("provider_error_rate", 0) * s.get("total", 0)
            secret_leak_total += m.get("secret_leak_count", 0)
        lines.append(f"- **total cases**: {total_cases}")
        lines.append(f"- **output_type_distribution**: {dict(sorted(ot_dist.items()))}")
        lines.append(f"- **tool_calls_avg**: {round(tool_calls_totals_sum / total_cases, 3) if total_cases else 0.0}")
        lines.append(f"- **duplicate_tool_call_rate**: {round(dedup_total / total_cases, 3) if total_cases else 0.0}")
        lines.append(f"- **timeout_rate**: {round(timeout_total / total_cases, 3) if total_cases else 0.0}")
        lines.append(f"- **no_progress_rate**: {round(no_progress_total / total_cases, 3) if total_cases else 0.0}")
        lines.append(f"- **provider_error_rate**: {round(error_total / total_cases, 3) if total_cases else 0.0}")
        lines.append(f"- **secret_leak_count**: {secret_leak_total}")
    else:
        lines.append("- (no data)")
    lines.append("")
    lines.append("## Top Failures")
    failures: list[dict[str, Any]] = []
    for suite in payload.get("suites", []):
        for row in suite.get("results", []):
            if not row.get("passed"):
                failures.append(row)
    for row in failures[:10]:
        run_result = dict(row.get("run_result") or {})
        checks = dict(row.get("checks") or {})
        failed_checks = [k for k, v in checks.items() if not bool(v)]
        model_calls = sum(1 for evt in list(run_result.get("events") or []) if str((evt or {}).get("type") or "") == "model_call_started")
        tool_calls_count = len(list(run_result.get("tool_calls") or []))
        output_type = str(run_result.get("output_type") or "answer")
        excerpt = str(run_result.get("final_answer") or "").replace("\n", " ").strip()[:120]
        lines.append(
            f"- `{row.get('case_id')}` ({row.get('suite')}): "
            f"score={row.get('score', 0.0):.2f}, "
            f"failed_checks={','.join(failed_checks) or 'none'}, "
            f"output_type={output_type}, "
            f"model_calls={model_calls}, "
            f"tool_calls_count={tool_calls_count}, "
            f"model_backend={payload.get('model_backend', 'unknown')}, "
            f"final_answer_excerpt={excerpt or '<empty>'}"
        )
    if not failures:
        lines.append("- none")
    lines.append("")
    lines.append("## Case Details")
    lines.append("")
    lines.append("| case_id | passed | failed_checks | output_type | tool_calls_count | stop_reason | risks |")
    lines.append("|---|---|---|---|---:|---|---|")
    for suite in payload.get("suites", []):
        for row in suite.get("results", []):
            run_result = dict(row.get("run_result") or {})
            checks = dict(row.get("checks") or {})
            failed_checks = [k for k, v in checks.items() if not bool(v)]
            tool_calls_count = len(list(run_result.get("tool_calls") or []))
            output_type = str(run_result.get("output_type") or "answer")
            stop_reason = str(run_result.get("stop_reason") or "")
            machine = dict((run_result.get("summary") or {}).get("machine") or {})
            risks = ", ".join([str(x) for x in list(machine.get("risks") or [])]) or "none"
            lines.append(
                f"| `{row.get('case_id')}` | `{row.get('passed')}` | "
                f"`{','.join(failed_checks) or 'none'}` | `{output_type}` | `{tool_calls_count}` | "
                f"`{stop_reason}` | {risks} |"
            )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Jarvis benchmark suites against AgentLoop.run_turn().")
    parser.add_argument("--suite", choices=SUITES, help="Run one suite")
    parser.add_argument("--max-cases", type=int, default=None, help="Case cap for selected suite")
    parser.add_argument("--all", action="store_true", help="Run all suites")
    parser.add_argument("--model-mode", choices=("auto", "fake", "real"), default="auto", help="Model backend mode")
    args = parser.parse_args()

    if not args.all and not args.suite:
        parser.error("either --suite or --all is required")

    selected = list(SUITES) if args.all else [str(args.suite)]
    suites = [run_suite(name, max_cases=args.max_cases if not args.all else None, model_mode=args.model_mode) for name in selected]
    first = suites[0] if suites else {}
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "all" if args.all else selected[0],
        "execution_mode": first.get("execution_mode", args.model_mode),
        "model_provider": first.get("model_provider", "unknown"),
        "model_name": first.get("model_name", "unknown"),
        "model_backend": first.get("model_backend", "unknown"),
        "suites": suites,
    }
    _write_reports(payload)
    print(json.dumps({"ok": True, "scope": payload["scope"], "suite_count": len(suites)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
