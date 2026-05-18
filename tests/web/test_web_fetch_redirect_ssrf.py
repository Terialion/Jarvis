from __future__ import annotations

from src.jarvis.web.fetch import run_web_fetch
from src.jarvis.web.fixtures import REDIRECT_TO_LOCALHOST_URL
from src.jarvis.web.schema import FetchRequest


def test_redirect_target_is_checked_by_ssrf_policy():
    result = run_web_fetch(FetchRequest(url=REDIRECT_TO_LOCALHOST_URL))
    run = result.runs[0]
    assert result.ok is False
    assert run["blocked"] is True
    assert run["ssrf_check_initial"] == "allowed"
    assert run["ssrf_check_final"] in {"loopback_blocked", "private_ip_blocked", "internal_hostname_blocked"}

