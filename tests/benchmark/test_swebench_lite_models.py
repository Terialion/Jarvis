from pathlib import Path

from jarvis.benchmarks.external.models import ExternalBenchmarkFailureType, ExternalBenchmarkResult, write_json


def test_swebench_lite_models_basic_contract(tmp_path: Path):
    result = ExternalBenchmarkResult(task_id="t1", instance_id="i1", failure_type=ExternalBenchmarkFailureType.SKIPPED.value)
    payload = result.to_dict()
    assert payload["schema_version"] == "jarvis.external_benchmark_result.v1"
    assert payload["failure_type"] in {t.value for t in ExternalBenchmarkFailureType}
    p = tmp_path / "result.json"
    write_json(p, payload)
    assert p.exists()

