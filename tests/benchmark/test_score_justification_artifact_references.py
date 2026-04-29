from pathlib import Path


def test_score_justification_exists():
    path = Path("d:/jarvis/docs/benchmarks/gate_score_justification.md")
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "Gate Score Justification" in text

