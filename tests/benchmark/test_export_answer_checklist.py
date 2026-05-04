from __future__ import annotations

import json
from pathlib import Path

from benchmarks import export_answer_checklist


def test_export_checklist_markdown_escape_and_json(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "benchmarks" / "reports").mkdir(parents=True, exist_ok=True)
    (tmp_path / "benchmarks" / "suites" / "jarvis_core").mkdir(parents=True, exist_ok=True)

    latest = {
        "generated_at": "2026-01-01T00:00:00Z",
        "scope": "jarvis_core",
        "execution_mode": "real_llm",
        "model_provider": "deepseek",
        "model_backend": "real",
        "suites": [
            {
                "suite": "jarvis_core",
                "model_backend": "real",
                "model_provider": "deepseek",
                "model_name": "deepseek-chat",
                "results": [
                    {
                        "case_id": "jarvis_core_001",
                        "passed": True,
                        "checks": {"must_call_tools": True},
                        "run_result": {
                            "final_answer": "A|B\nline2\tcol",
                            "stop_reason": "completed",
                            "tool_calls": [{"name": "repo_reader.read_file"}],
                            "events": [{"type": "model_call_started", "payload": {"text": "x"}}],
                            "summary": {"machine": {"risks": ["r1"], "tools_used": ["repo_reader.read_file"]}},
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
        "category": "repo",
        "input": "读取 README.md",
        "expected_behavior": {"must_call_tools": True},
    }
    (tmp_path / "benchmarks" / "suites" / "jarvis_core" / "cases.jsonl").write_text(
        json.dumps(case_row, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    rc = export_answer_checklist.main()
    assert rc == 0

    md = (tmp_path / "temp" / "benchmark_answer_checklist.md").read_text(encoding="utf-8")
    assert r"A\|B line2 col" in md
    assert "`completed`" in md

    raw_json = (tmp_path / "temp" / "benchmark_answer_checklist.json").read_text(encoding="utf-8")
    payload = json.loads(raw_json)
    assert isinstance(payload, dict)
    assert payload["rows"][0]["stop_reason"] == "completed"

