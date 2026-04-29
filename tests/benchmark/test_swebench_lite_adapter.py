from pathlib import Path

from jarvis.benchmarks.external.models import ExternalBenchmarkRunConfig
from jarvis.benchmarks.external.swebench_adapter import SwebenchLiteAdapter


def test_swebench_adapter_dry_run_generates_report():
    root = Path("d:/jarvis")
    fixture = root / "temp/external_benchmarks/swebench_lite/fixtures/fake_tasks.jsonl"
    fixture.parent.mkdir(parents=True, exist_ok=True)
    fixture.write_text(
        '{"instance_id":"fake__repo-0001","repo":"fake/repo","base_commit":"fake_base","problem_statement":"Fix","version":"fake"}\n',
        encoding="utf-8",
    )
    adapter = SwebenchLiteAdapter(root)
    report = adapter.run(ExternalBenchmarkRunConfig(dry_run=True, allow_online=False, max_tasks=1))
    assert report["dry_run"] is True
    assert report["summary"]["total"] == 1
    assert report["summary"]["patch_generated"] >= 1

