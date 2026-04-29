from pathlib import Path

from jarvis.benchmarks.external.evidence_adapter import SwebenchEvidenceAdapter


def test_evidence_adapter_generates_paths(tmp_path: Path):
    adapter = SwebenchEvidenceAdapter(tmp_path)
    ev = adapter.build_for_task("fake__repo-0001", {"patch": "diff --git", "prediction_path": "p.jsonl"})
    assert Path(ev.operator_evidence_path).exists()
    assert Path(ev.replay_evidence_path).exists()
    assert Path(ev.patch_review_path).exists()

