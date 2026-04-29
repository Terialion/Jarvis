from __future__ import annotations

from pathlib import Path


def test_jarvis_core_resolves_to_modern_src_package() -> None:
    import jarvis.core as core  # type: ignore

    core_path = Path(core.__file__).resolve().as_posix()

    assert "/src/jarvis/core/" in core_path, core_path
    assert not core_path.endswith("/rubbish/legacy/jarvis_core_legacy.py"), core_path
    assert not core_path.endswith("/jarvis/core.py"), core_path

