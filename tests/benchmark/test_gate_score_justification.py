from pathlib import Path


def test_gate_score_justification_exists():
    p = Path("d:/jarvis/docs/benchmarks/gate_score_justification.md")
    assert p.exists()
    text = p.read_text(encoding="utf-8")
    assert "Group Scores" in text
