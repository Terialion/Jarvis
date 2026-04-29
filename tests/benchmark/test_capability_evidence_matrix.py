from pathlib import Path


def test_capability_evidence_matrix_exists_after_benchmark():
    p = Path("d:/jarvis/docs/benchmarks/capability_evidence_matrix.md")
    assert p.exists()
    text = p.read_text(encoding="utf-8")
    assert "Capability Group" in text
