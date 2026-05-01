from src.jarvis.core.commands.registry import list_command_metadata, resolve_command_metadata


def test_command_registry_exposes_metadata_fields():
    meta = resolve_command_metadata("/context")
    assert meta is not None
    assert meta.name == "/context"
    assert meta.description
    assert meta.dispatch == "local"


def test_command_registry_preserves_argument_hint_and_allowed_tools_shape():
    meta = resolve_command_metadata("/test")
    assert meta is not None
    assert isinstance(meta.argument_hint, str) or meta.argument_hint is None
    assert isinstance(meta.allowed_tools, list)
    assert meta.dispatch == "tool"


def test_allowed_tools_only_narrow_scope():
    rows = list_command_metadata()
    assert rows
    for row in rows:
        assert isinstance(row.allowed_tools, list)
