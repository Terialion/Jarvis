from __future__ import annotations

from dataclasses import dataclass

from src.jarvis.web.fetch import FetchTransportResponse, run_web_fetch
from src.jarvis.web.fixtures import FLINK_OFFICIAL_URL
from src.jarvis.web.schema import FetchRequest


def test_web_fetch_success_marks_document_untrusted():
    result = run_web_fetch(FetchRequest(url=FLINK_OFFICIAL_URL, max_chars=120))

    assert result.ok is True
    assert result.runs[0]["status_code"] == 200
    assert result.documents[0]["is_untrusted"] is True
    assert len(result.documents[0]["text"]) <= 120


@dataclass
class SecretFixtureTransport:
    def fetch(self, url: str, *, timeout_s: int = 10, max_bytes: int = 2_000_000) -> FetchTransportResponse:
        _ = timeout_s, max_bytes
        return FetchTransportResponse(
            url=url,
            final_url=url,
            text="<title>Secret Page</title> OPENAI_API_KEY=abc123 password=hunter2 token=abc sk-test-secret",
            status_code=200,
            content_type="text/html",
        )


def test_web_fetch_redacts_secret_like_content():
    result = run_web_fetch(
        FetchRequest(url="https://safe.example/secret", max_chars=500),
        transport=SecretFixtureTransport(),
    )

    text = result.documents[0]["text"]
    assert result.ok is True
    assert "OPENAI_API_KEY=" not in text
    assert "password=" not in text
    assert "token=" not in text
    assert "sk-test-secret" not in text
