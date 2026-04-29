from pathlib import Path


def test_minimal_agent_loop_doc_mentions_trace_artifact():
    doc = Path("d:/jarvis/docs/architecture/minimal_agent_loop.md")
    assert doc.exists()
    text = doc.read_text(encoding="utf-8")
    assert "minimal_loop_trace.json" in text or "minimal_agent_loop_demo.json" in text

