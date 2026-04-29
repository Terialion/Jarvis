from pathlib import Path


def test_reference_architecture_doc_exists():
    doc = Path("d:/jarvis/docs/architecture/jarvis_vs_references.md")
    assert doc.exists()
    assert "Jarvis" in doc.read_text(encoding="utf-8")

