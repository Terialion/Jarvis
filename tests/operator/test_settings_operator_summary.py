from jarvis.core.settings.models import SettingsBundle
from jarvis.core.settings.resolver import SettingsResolver


def test_effective_settings_include_runtime_override():
    merged = SettingsResolver.resolve(
        SettingsBundle(
            defaults={"sandbox_mode": "restricted"},
            global_settings={"sandbox_mode": "workspace-write"},
            runtime_overrides={"sandbox_mode": "read-only"},
        )
    )
    assert merged["sandbox_mode"] == "read-only"

