from src.jarvis.core.routing.input_gateway import build_input_envelope


def test_input_envelope_is_structural_only():
    envelope = build_input_envelope("你好啊")
    assert hasattr(envelope, "raw_text")
    assert not hasattr(envelope, "intent")
    assert not hasattr(envelope, "response_mode")


def test_input_envelope_detects_slash_command_and_args():
    envelope = build_input_envelope("/task 115")
    assert envelope.slash.is_slash_command is True
    assert envelope.slash.command_name == "task"
    assert envelope.slash.raw_args == "115"
    assert envelope.slash.args_tokens == ["115"]


def test_input_envelope_distinguishes_unix_path_from_slash_command():
    envelope = build_input_envelope("/Users/a/file.py")
    assert envelope.slash.is_slash_command is False
    assert envelope.slash.looks_like_path is True
    assert "/Users/a/file.py" in envelope.path_hints


def test_input_envelope_collects_sensitive_hints_and_urls():
    envelope = build_input_envelope("读取 .env 看看 https://example.com")
    assert envelope.has_url is True
    assert "https://example.com" in envelope.urls
    assert ".env" in envelope.sensitive_hints
