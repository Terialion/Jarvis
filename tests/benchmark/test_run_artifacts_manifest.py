import json
from pathlib import Path


def test_run_artifacts_manifest_exists_and_lists_artifacts():
    p = Path("d:/jarvis/temp/gap_closure/run_artifacts_manifest.json")
    assert p.exists()
    payload = json.loads(p.read_text(encoding="utf-8"))
    assert isinstance(payload.get("artifacts"), list)
    assert len(payload["artifacts"]) >= 6
