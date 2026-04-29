from pathlib import Path


def test_quickstart_present_in_minimal_loop_doc():
    doc = Path("d:/jarvis/docs/architecture/minimal_agent_loop.md")
    assert doc.exists()
    text = doc.read_text(encoding="utf-8").lower()
    assert "demo" in text or "quickstart" in text

