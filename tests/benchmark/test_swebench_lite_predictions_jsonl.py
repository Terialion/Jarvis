import json
from pathlib import Path

from jarvis.benchmarks.external.swebench_adapter import SwebenchLiteAdapter


def test_predictions_jsonl_format(tmp_path: Path):
    adapter = SwebenchLiteAdapter(Path("d:/jarvis"))
    out = adapter.write_predictions_jsonl(tmp_path, [{"instance_id": "a", "model_patch": "diff --git"}])
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert "instance_id" in row
    assert "model_patch" in row

