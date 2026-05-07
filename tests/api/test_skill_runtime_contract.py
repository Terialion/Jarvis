from __future__ import annotations

from pathlib import Path

from src.jarvis.api.server import JarvisApiState, route_request


def test_agent_run_returns_skill_runtime_fields(tmp_path: Path):
    (tmp_path / "README.md").write_text("# API Skill\n\nRuntime contract.", encoding="utf-8")
    state = JarvisApiState()

    status, payload = route_request(
        state,
        "POST",
        "/api/agent/run",
        {
            "text": "summarize README.md",
            "model_mode": "fake",
            "project_root": str(tmp_path),
        },
    )

    assert status == 200
    result = payload["result"]
    assert result["skills_used"] == ["summarize_file"]
    assert result["skill_calls_count"] == 1
    assert result["skill_results"][0]["skill_name"] == "summarize_file"
    assert result["summary"]["machine"]["handoff_summary"]
