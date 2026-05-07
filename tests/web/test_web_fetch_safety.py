from __future__ import annotations

import pytest

from src.jarvis.web.fetch import run_web_fetch
from src.jarvis.web.fixtures import REDIRECT_TO_LOCALHOST_URL
from src.jarvis.web.safety import assert_safe_url, block_reason_for_url
from src.jarvis.web.schema import FetchRequest


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        ("file:///etc/passwd", "unsupported_scheme"),
        ("http://localhost:8000/private", "internal_hostname_blocked"),
        ("http://127.0.0.1:8000/private", "loopback_blocked"),
        ("http://10.0.0.1/private", "private_ip_blocked"),
        ("http://169.254.169.254/latest/meta-data", "metadata_service_blocked"),
    ],
)
def test_url_safety_blocks_internal_targets(url: str, reason: str):
    assert block_reason_for_url(url) == reason
    with pytest.raises(ValueError, match=reason):
        assert_safe_url(url)


def test_web_fetch_blocks_redirect_to_private_ip():
    result = run_web_fetch(FetchRequest(url=REDIRECT_TO_LOCALHOST_URL))

    assert result.ok is False
    assert result.documents == []
    assert result.runs[0]["blocked"] is True
    assert result.runs[0]["block_reason"] == "loopback_blocked"
