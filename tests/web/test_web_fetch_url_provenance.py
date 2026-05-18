from __future__ import annotations

from src.jarvis.web.fetch import run_web_fetch
from src.jarvis.web.fixtures import FLINK_OFFICIAL_URL
from src.jarvis.web.schema import FetchRequest


def test_fetch_run_records_url_provenance_fields():
    request = FetchRequest(
        url=FLINK_OFFICIAL_URL,
        provenance={
            "url_source": "search_result_url",
            "guided_by_skill": "multi-search-engine",
            "invocation_path": "reference_skill_guided_tool_call",
            "domain_policy_result": "allow",
        },
    )
    result = run_web_fetch(request)
    run = result.runs[0]
    assert run["url_source"] == "search_result_url"
    assert run["guided_by_skill"] == "multi-search-engine"
    assert run["invocation_path"] == "reference_skill_guided_tool_call"
    assert run["domain_policy_result"] == "allow"
    assert run["ssrf_check_initial"] == "allowed"
    assert run["ssrf_check_final"] == "allowed"

