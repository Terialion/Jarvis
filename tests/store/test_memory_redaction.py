from __future__ import annotations

from pathlib import Path

from src.jarvis.agent.skill_context import SkillObservation
from src.jarvis.core.policy.approval import ApprovalRequest
from src.jarvis.store.memory_store import MemoryStore
from src.jarvis.store.thread_store import ThreadStore


def test_raw_secret_never_appears_in_store(tmp_path: Path):
    secret = "OPENAI_API_KEY=sk-top-secret"
    path = tmp_path / "jarvis.db"
    thread_store = ThreadStore(db_path=path)
    memory_store = MemoryStore(db_path=path)
    thread = thread_store.create_thread(title="Redaction")
    thread_store.append_message(thread.thread_id, "user", secret)
    thread_store.append_tool_call(thread.thread_id, "turn_001", {"id": "call_001", "name": "web.fetch", "arguments": {"Authorization": f"Bearer {secret}"}})
    thread_store.append_tool_result(thread.thread_id, "turn_001", {"call_id": "call_001", "name": "web.fetch", "ok": True, "content": secret})
    thread_store.append_skill_observation(thread.thread_id, SkillObservation(skill_name="repo_overview", summary=secret, facts={"token": secret}), turn_id="turn_001")
    thread_store.append_approval_audit(
        thread.thread_id,
        "turn_001",
        ApprovalRequest(
            approval_id="approval_001",
            tool_name="command_runner.run",
            arguments_preview={"command": f"echo {secret}"},
            risk_level="high",
            reason=secret,
            created_at="2026-05-07T00:00:00+00:00",
            status="pending",
        ),
    )
    memory_store.set_user_memory("secret", secret)

    raw = path.read_bytes()
    assert secret.encode("utf-8") not in raw
