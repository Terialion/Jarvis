from __future__ import annotations

from pathlib import Path

from src.jarvis.core.policy.approval import ApprovalRequest, ApprovalResponse
from src.jarvis.store import ThreadStore


def test_approval_audit_persists_redacted_records(tmp_path: Path):
    path = tmp_path / "jarvis.db"
    store = ThreadStore(sessions_dir=path)
    thread = store.create_thread(title="Approval audit")
    secret = "OPENAI_API_KEY=sk-audit-secret"
    store.append_approval_audit(
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
    store.append_approval_audit(
        thread["thread_id"],
        "turn_001",
        ApprovalResponse(
            approval_id="approval_001",
            decision="approved",
            reason=secret,
            decided_at="2026-05-07T00:01:00+00:00",
            decided_by="tester",
        ),
    )

    rows = store.get_approval_audits(thread["thread_id"])
    assert rows
    assert all(secret not in str(row["reason_redacted"] or "") for row in rows)
