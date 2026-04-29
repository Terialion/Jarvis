from jarvis.cli import _mask_secret_like


def test_cli_secret_masking_no_raw_key():
    raw = "api_key=sk-test-1234567890 token=abc"
    masked = _mask_secret_like(raw)
    assert "1234567890" not in masked
    assert "api_key=****" in masked
    assert "token=****" in masked
