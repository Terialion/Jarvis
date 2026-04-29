import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from jarvis.benchmarks.artifact_bootstrap import (
    bootstrap_gap_closure_artifacts,
    ensure_fresh_artifact,
    is_stale_artifact,
)


def test_is_stale_artifact_contract(tmp_path: Path):
    target = tmp_path / "operator_api_verification.json"
    target.write_text(json.dumps({"ok": False, "run_id": "old", "generated_at": "2020-01-01T00:00:00"}) + "\n", encoding="utf-8")
    assert is_stale_artifact(target, "run_new") is True

    target.write_text(json.dumps({"ok": True, "run_id": "run_new"}) + "\n", encoding="utf-8")
    assert is_stale_artifact(target, "run_new") is True  # missing generated_at

    target.write_text(json.dumps({"ok": True, "run_id": "run_new", "generated_at": "2026-04-28T00:00:00"}) + "\n", encoding="utf-8")
    assert is_stale_artifact(target, "run_new") is False


def test_ensure_fresh_artifact_overwrites_stale(tmp_path: Path):
    target = tmp_path / "artifact.json"
    target.write_text(json.dumps({"ok": False, "run_id": "old"}) + "\n", encoding="utf-8")
    meta = ensure_fresh_artifact(target, "run_x", {"schema_version": "v1", "ok": True})
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert meta["stale_replaced"] is True
    assert payload["run_id"] == "run_x"
    assert payload["ok"] is True
    assert payload["source"] == "benchmark_bootstrap"
    assert payload.get("generated_at")


def test_bootstrap_summary_includes_freshness(tmp_path: Path):
    out = bootstrap_gap_closure_artifacts(tmp_path, "run_abc")
    fresh = out["artifact_freshness"]["operator_api_verification.json"]
    assert fresh["fresh"] is True
    assert fresh["run_id"] == "run_abc"
    payload = json.loads((tmp_path / "operator_api_verification.json").read_text(encoding="utf-8"))
    assert payload["run_id"] == "run_abc"
    assert payload.get("generated_at")
    assert payload["source"] == "benchmark_bootstrap"
