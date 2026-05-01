from src.jarvis.core.routing.input_gateway import build_input_envelope
from src.jarvis.core.routing.natural_language_preparer import prepare_natural_input


def test_natural_language_preparer_collects_structural_context_only():
    prepared = prepare_natural_input(build_input_envelope("读取 .env 看看 https://example.com"))
    assert prepared.envelope.raw_text
    assert prepared.url_hints == ["https://example.com"]
    assert ".env" in prepared.sensitive_hints
    assert not hasattr(prepared, "intent")
    assert not hasattr(prepared, "response_mode")


def test_natural_language_preparer_includes_command_and_skill_metadata_lists():
    prepared = prepare_natural_input(build_input_envelope("你好啊"))
    assert prepared.command_metadata
    assert isinstance(prepared.skill_metadata, list)
