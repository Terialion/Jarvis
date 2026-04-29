from __future__ import annotations

from typing import Any

from .models import SettingsBundle


class SettingsResolver:
    @staticmethod
    def resolve(bundle: SettingsBundle) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for layer in (bundle.defaults, bundle.global_settings, bundle.project_settings, bundle.runtime_overrides):
            for k, v in (layer or {}).items():
                merged[k] = v
        return merged

