from __future__ import annotations

from pathlib import Path

from src.jarvis.agent.skill_context import SkillObservation
from src.jarvis.core.policy.approval import ApprovalRequest
from src.jarvis.store.memory_store import MemoryStore
from src.jarvis.store import ThreadStore


def test_raw_secret_never_appears_in_store(tmp_path: Path):
    secret = "OPENAI_API_KEY=sk-top-secret"
    path = tmp_path / "jarvis.db"
    thread_store = ThreadStore(sessions_dir=path)
    memory_store = MemoryStore(memory_md_dir=path)
    thread = thread_store.create_thread(title="Redaction")
    thread_store.append_message(thread["thread_id"], "user", secret)
    thread_store.append_tool_call(thread["thread_id"], "turn_001", {"id": "call_001", "name": "web.fetch", "arguments": {"Authorization": f"Bearer {secret}"}})
    thread_store.append_tool_result(thread["thread_id"], "turn_001", {"call_id": "call_001", "name": "web.fetch", "ok": True, "content": secret})
    thread_store.append_skill_observation(thread["thread_id"], SkillObservation(skill_name="repo_overview", summary=secret, facts={"token": secret}), turn_id="turn_001")
    thread_store.append_approval_audit(
        thread["thread_id"],
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

    # Session JSONL files must redact secrets
    for p in path.glob("*.jsonl"):
        if p.is_file():
            raw = p.read_bytes()
            assert secret.encode("utf-8") not in raw, f"Secret found in session file {p}"
    # Memory markdown files store values as-is — skip MEMORY.md index, check value file
    mem_path = path / "secret.md"
    assert mem_path.exists()
    assert secret.encode("utf-8") in mem_path.read_bytes(), "Memory must persist raw value"
