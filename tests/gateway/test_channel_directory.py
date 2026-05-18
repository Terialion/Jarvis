from src.jarvis.gateway import default_channel_directory
from src.jarvis.gateway.schema import ChannelSpec


def test_channel_directory_default_and_toggle():
    directory = default_channel_directory()
    names = {c.name for c in directory.list_channels()}
    assert {"api", "cli", "control_surface", "mock_mcp"}.issubset(names)
    directory.register_channel(ChannelSpec(name="x", kind="mock", enabled=True, permissions_profile="strict"))
    assert directory.get_channel("x") is not None
    directory.disable_channel("x")
    assert directory.get_channel("x").enabled is False
