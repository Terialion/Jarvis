from pathlib import Path


def test_minimal_agent_loop_doc_has_required_sections():
    p = Path("d:/jarvis/docs/architecture/minimal_agent_loop.md")
    assert p.exists()
    text = p.read_text(encoding="utf-8")
    required = [
        "User input",
        "Intent / Policy",
        "Tool call",
        "Approval",
        "Replay",
        "Memory",
        "Final response",
    ]
    for key in required:
        assert key in text
