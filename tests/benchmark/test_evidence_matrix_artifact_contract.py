from pathlib import Path


def test_evidence_matrix_references_artifacts():
    path = Path("d:/jarvis/docs/benchmarks/capability_evidence_matrix.md")
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "Capability Evidence Matrix" in text

