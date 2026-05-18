from __future__ import annotations

from .channel_directory import ChannelDirectory, default_channel_directory


def ensure_channel_directory(directory: ChannelDirectory | None = None) -> ChannelDirectory:
    return directory or default_channel_directory()

