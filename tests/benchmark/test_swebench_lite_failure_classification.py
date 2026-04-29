from pathlib import Path

from jarvis.benchmarks.external.models import ExternalBenchmarkFailureType
from jarvis.benchmarks.external.swebench_adapter import SwebenchLiteAdapter


def test_environment_failure_not_agent_failure():
    adapter = SwebenchLiteAdapter(Path("d:/jarvis"))
    failure = adapter.classify_failure(
        patch_generated=True,
        harness_result={"failure_type": ExternalBenchmarkFailureType.ENVIRONMENT_FAILURE.value},
        env={"docker_available": False},
        allow_online=True,
    )
    assert failure == ExternalBenchmarkFailureType.ENVIRONMENT_FAILURE.value
    assert failure != ExternalBenchmarkFailureType.AGENT_FAILURE.value

