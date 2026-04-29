import json
from pathlib import Path


def test_rethink_group_exists_in_ledger():
    ledger = json.loads(Path("d:/jarvis/docs/benchmarks/gap_ledger.json").read_text(encoding="utf-8"))
    groups = [e.get("capability_group") for e in ledger.get("entries", [])]
    assert "rethink_replan_recovery" in groups
