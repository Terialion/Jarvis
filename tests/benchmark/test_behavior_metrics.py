from __future__ import annotations

import json
from pathlib import Path

from benchmarks import export_answer_checklist, run_benchmark


def test_compute_behavior_metrics_all_fields():
    rows = [
        {
            "run_result": {
                "output_type": "answer",
                "tool_calls": [{"name": "repo_reader.read_file"}],
                "events": [],
                "stop_reason": "completed",
                "final_answer": "plain answer",
            }
        },
        {
            "run_result": {
                "output_type": "refusal",
                "tool_calls": [],
                "events": [],
                "stop_reason": "completed",
                "final_answer": "refused",
            }
        },
        {
            "run_result": {
                "output_type": "clarification",
                "tool_calls": [],
                "events": [],
                "stop_reason": "no_progress",
                "final_answer": "please clarify",
            }
        },
        {
            "run_result": {
                "output_type": "error",
                "tool_calls": [],
                "events": [{"type": "tool_call_deduped"}],
                "stop_reason": "timeout",
                "final_answer": "sk-test-leak",
            }
        },
    ]
    metrics = run_benchmark._compute_suite_metrics(rows)
    assert metrics["output_type_distribution"] == {
        "answer": 1,
        "refusal": 1,
        "clarification": 1,
        "error": 1,
    }
    assert metrics["tool_calls_avg"] == 0.25
    assert metrics["duplicate_tool_call_rate"] > 0
    assert metrics["timeout_rate"] > 0
    assert metrics["no_progress_rate"] > 0
    assert metrics["provider_error_rate"] > 0
    assert metrics["secret_leak_count"] > 0


def test_render_markdown_includes_behavior_metrics_section():
    payload = {
        "generated_at": "2026-01-01T00:00:00Z",
        "scope": "jarvis_core",
        "execution_mode": "fake_model",
        "model_provider": "fake",
        "model_name": "fake-agent-v0",
        "model_backend": "fake",
        "suites": [
            {
                "suite": "jarvis_core",
                "total": 4,
                "pass_rate": 1.0,
                "metrics": {
                    "output_type_distribution": {
                        "answer": 1,
                        "refusal": 1,
                        "clarification": 1,
                        "error": 1,
                    },
                    "tool_calls_avg": 0.25,
                    "duplicate_tool_call_rate": 0.25,
                    "timeout_rate": 0.25,
                    "no_progress_rate": 0.25,
                    "provider_error_rate": 0.25,
                    "secret_leak_count": 1,
                },
                "results": [],
            }
        ],
    }
    rendered = run_benchmark._render_markdown(payload)
    assert "## Behavior Metrics" in rendered
    assert "output_type_distribution" in rendered
    assert "tool_calls_avg" in rendered
    assert "duplicate_tool_call_rate" in rendered
    assert "timeout_rate" in rendered
    assert "no_progress_rate" in rendered
    assert "provider_error_rate" in rendered
    assert "secret_leak_count" in rendered


def test_export_checklist_rows_include_output_type(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "benchmarks" / "reports").mkdir(parents=True, exist_ok=True)
    (tmp_path / "benchmarks" / "suites" / "jarvis_core").mkdir(parents=True, exist_ok=True)

    latest = {
        "generated_at": "2026-01-01T00:00:00Z",
        "scope": "jarvis_core",
        "execution_mode": "fake_model",
        "model_provider": "fake",
        "model_backend": "fake",
        "suites": [
            {
                "suite": "jarvis_core",
                "model_backend": "fake",
                "model_provider": "fake",
                "model_name": "fake-agent-v0",
                "results": [
                    {
                        "case_id": "jarvis_core_001",
                        "passed": True,
                        "checks": {"must_call_tools": True},
                        "run_result": {
                            "output_type": "clarification",
                            "final_answer": "please clarify",
                            "stop_reason": "needs_user_clarification",
                            "tool_calls": [],
                            "events": [{"type": "turn_started", "payload": {"text": "帮我弄一下"}}],
                            "summary": {"machine": {"risks": [], "tools_used": []}},
                        },
                    }
                ],
            }
        ],
    }
    (tmp_path / "benchmarks" / "reports" / "latest.json").write_text(
        json.dumps(latest, ensure_ascii=False),
        encoding="utf-8",
    )
    case_row = {
        "id": "jarvis_core_001",
        "suite": "jarvis_core",
        "category": "behavioral",
        "input": "帮我弄一下",
        "expected_behavior": {"must_clarify": True},
    }
    (tmp_path / "benchmarks" / "suites" / "jarvis_core" / "cases.jsonl").write_text(
        json.dumps(case_row, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    rc = export_answer_checklist.main()
    assert rc == 0

    checklist_md = (tmp_path / "temp" / "benchmark_answer_checklist.md").read_text(encoding="utf-8")
    checklist_json = json.loads((tmp_path / "temp" / "benchmark_answer_checklist.json").read_text(encoding="utf-8"))
    assert "output_type" in checklist_md
    assert checklist_json["rows"][0]["output_type"] == "clarification"

