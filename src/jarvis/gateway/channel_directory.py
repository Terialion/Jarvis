from __future__ import annotations

from dataclasses import replace

from .schema import ChannelSpec


class ChannelDirectory:
    def __init__(self, channels: list[ChannelSpec] | None = None) -> None:
        self._channels: dict[str, ChannelSpec] = {}
        for channel in channels or []:
            self._channels[channel.name] = channel

    def list_channels(self) -> list[ChannelSpec]:
        return list(self._channels.values())

    def register_channel(self, spec: ChannelSpec) -> ChannelSpec:
        self._channels[spec.name] = spec
        return spec

    def enable_channel(self, name: str) -> ChannelSpec | None:
        channel = self._channels.get(name)
        if channel is None:
            return None
        updated = replace(channel, enabled=True)
        self._channels[name] = updated
        return updated

    def disable_channel(self, name: str) -> ChannelSpec | None:
        channel = self._channels.get(name)
        if channel is None:
            return None
        updated = replace(channel, enabled=False)
        self._channels[name] = updated
        return updated

    def get_channel(self, name: str) -> ChannelSpec | None:
        return self._channels.get(name)

    def permissions_for_channel(self, name: str) -> str:
        channel = self.get_channel(name)
        if channel is None:
            return "strict"
        return channel.permissions_profile


def default_channel_directory() -> ChannelDirectory:
    return ChannelDirectory(
        channels=[
            ChannelSpec(name="api", kind="api", enabled=True, permissions_profile="workspace_write"),
            ChannelSpec(name="cli", kind="cli", enabled=True, permissions_profile="workspace_write"),
            ChannelSpec(name="control_surface", kind="control_surface", enabled=True, permissions_profile="read_only"),
            ChannelSpec(name="mock_mcp", kind="mcp", enabled=True, permissions_profile="strict"),
        ]
    )

