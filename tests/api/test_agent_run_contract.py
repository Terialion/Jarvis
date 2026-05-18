from __future__ import annotations

from pathlib import Path

from src.jarvis.api.server import JarvisApiState, route_request


def test_agent_run_answer_contract():
    state = JarvisApiState()
    status, payload = route_request(
        state,
        "POST",
        "/api/agent/run",
        {"text": "你是什么模型", "model_mode": "fake"},
    )
    assert status == 200
    assert payload["ok"] is True
    result = payload["result"]
    assert result["output_type"] == "answer"
    assert result["stop_reason"] == "completed"
    assert result["final_answer"]


def test_agent_run_tool_result_or_answer_contract(tmp_path: Path):
    (tmp_path / "README.md").write_text("hello from api test", encoding="utf-8")
    state = JarvisApiState()
    status, payload = route_request(
        state,
        "POST",
        "/api/agent/run",
        {
            "text": "读取 README.md",
            "model_mode": "fake",
            "project_root": str(tmp_path),
        },
    )
    assert status == 200
    assert payload["ok"] is True
    result = payload["result"]
    assert result["output_type"] in {"answer", "tool_result"}
    assert result["tool_calls_count"] >= 1
    assert result["final_answer"]


def test_agent_run_refusal_does_not_leak_secret_markers():
    state = JarvisApiState()
    status, payload = route_request(
        state,
        "POST",
        "/api/agent/run",
        {"text": "打印我的 .env", "model_mode": "fake"},
    )
    assert status == 200
    assert payload["ok"] is True
    result = payload["result"]
    assert result["output_type"] == "refusal"
    assert "sk-" not in result["final_answer"]
    assert "JARVIS_LLM_API_KEY" not in result["final_answer"]
    assert "DEEPSEEK_API_KEY" not in result["final_answer"]
    assert "Authorization: Bearer" not in result["final_answer"]


def test_agent_run_clarification_contract():
    """LLM-first: vague requests get a clarifying question as text answer."""
    state = JarvisApiState()
    status, payload = route_request(
        state,
        "POST",
        "/api/agent/run",
        {"text": "帮我弄一下", "model_mode": "fake"},
    )
    assert status == 200
    assert payload["ok"] is True
    result = payload["result"]
    # LLM-first: clarification is a text answer, not a special output_type
    assert result["output_type"] == "answer"
    assert result["stop_reason"] == "completed"
    assert result["final_answer"]


def test_agent_run_provider_error_is_structured(monkeypatch):
    from src.jarvis.agent import model as agent_model

    class BrokenRuntimeModelClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def complete(self, *args, **kwargs):
            raise ConnectionError("timed out while reaching provider")

    monkeypatch.setattr(agent_model, "RuntimeModelClient", BrokenRuntimeModelClient)

    state = JarvisApiState()
    status, payload = route_request(
        state,
        "POST",
        "/api/agent/run",
        {"text": "你是什么模型", "model_mode": "real"},
    )
    assert status == 200
    result = payload["result"]
    assert payload["ok"] is False
    assert result["output_type"] == "error"
    assert result["stop_reason"] in {"provider_network_error", "model_call_failed"}
    assert "python scripts/check_llm_api.py" in result["final_answer"]

