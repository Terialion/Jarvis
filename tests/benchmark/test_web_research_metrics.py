from __future__ import annotations

from benchmarks import run_benchmark


def test_web_research_metrics_compute_expected_fields():
    rows = [
        {
            "suite": "web_research",
            "category": "fetch_safety",
            "run_result": {
                "output_type": "partial",
                "stop_reason": "insufficient_evidence",
                "final_answer": "blocked safely",
                "events": [{"type": "web_search_started"}, {"type": "web_fetch_started"}, {"type": "web_fetch_blocked"}],
                "tool_calls": [{"name": "web.search"}, {"name": "web.fetch"}],
                "summary": {
                    "machine": {
                        "web_search_runs_count": 1,
                        "web_fetch_runs_count": 0,
                        "web_fetch_blocked_count": 1,
                        "evidence_count": 0,
                        "official_sources_count": 0,
                        "github_sources_count": 0,
                        "citation_count": 0,
                        "source_coverage_score": 0.0,
                    }
                },
            },
        },
        {
            "suite": "web_research",
            "category": "prompt_injection_safety",
            "run_result": {
                "output_type": "answer",
                "stop_reason": "completed",
                "final_answer": "safe answer with https://docs.example.com/prompt-injection-test",
                "events": [{"type": "web_search_started"}, {"type": "web_fetch_started"}],
                "tool_calls": [{"name": "web.search"}, {"name": "web.fetch"}],
                "summary": {
                    "machine": {
                        "web_search_runs_count": 1,
                        "web_fetch_runs_count": 1,
                        "web_fetch_blocked_count": 0,
                        "evidence_count": 2,
                        "official_sources_count": 1,
                        "github_sources_count": 0,
                        "citation_count": 1,
                        "prompt_injection_blocked": True,
                        "source_coverage_score": 0.8,
                    }
                },
            },
        },
    ]

    metrics = run_benchmark._compute_suite_metrics(rows)["web_research_metrics"]

    assert metrics["web_search_success_rate"] == 1.0
    assert metrics["web_fetch_success_rate"] == 0.5
    assert metrics["web_fetch_blocked_count"] == 1
    assert metrics["official_source_rate"] == 0.5
    assert metrics["prompt_injection_blocked_count"] == 1
    assert metrics["web_secret_leak_count"] == 0


def test_render_markdown_includes_web_research_metrics_section():
    rendered = run_benchmark._render_markdown(
        {
            "generated_at": "2026-01-01T00:00:00Z",
            "scope": "web_research",
            "behavior_metrics": {"total_cases": 1, "output_type_distribution": {"answer": 1}},
            "web_research_metrics": {"web_search_success_rate": 1.0, "prompt_injection_blocked_count": 1},
            "suites": [],
        }
    )

    assert "## Web Research Metrics" in rendered
    assert "web_search_success_rate" in rendered
    assert "prompt_injection_blocked_count" in rendered
