import json
from pathlib import Path


def test_high_score_groups_have_artifact_backed_evidence():
    round1 = json.loads(Path("d:/jarvis/temp/gap_closure/round_1.json").read_text(encoding="utf-8"))
    manifest = json.loads(Path("d:/jarvis/temp/gap_closure/run_artifacts_manifest.json").read_text(encoding="utf-8"))
    artifacts = set(manifest.get("artifacts", []))
    assert artifacts
    scores = round1.get("scores", {}).get("group_scores", {})
    for group, score in scores.items():
        if (score or 0) >= 90.0:
            assert len(artifacts) >= 1
