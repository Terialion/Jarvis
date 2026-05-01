from pathlib import Path

import jarvis.cli
import src.jarvis.core.cli_response
import src.jarvis.core.coding_loop
import src.jarvis.core.repo_inspection
import src.jarvis.core.routing


def _posix(module) -> str:
    return Path(module.__file__).as_posix()


def test_import_path_boundaries() -> None:
    assert _posix(jarvis.cli).endswith("/jarvis/cli.py")
    assert "/src/jarvis/core/routing" in _posix(src.jarvis.core.routing)
    assert "/src/jarvis/core/cli_response" in _posix(src.jarvis.core.cli_response)
    assert "/src/jarvis/core/repo_inspection" in _posix(src.jarvis.core.repo_inspection)
    assert "/src/jarvis/core/coding_loop" in _posix(src.jarvis.core.coding_loop)

