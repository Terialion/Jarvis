from pathlib import Path

from src.jarvis.core.instructions import DEFAULT_JARVIS_MD


def test_default_jarvis_md_has_required_sections() -> None:
    for heading in [
        "Project Overview",
        "CLI Behavior",
        "Language Policy",
        "Capability Answer Policy",
        "Usage Help Policy",
        "Repo Inspection Policy",
        "Coding Task Policy",
        "Loop Policy",
        "Success Judge Policy",
        "Rethink/Replan Policy",
        "Test Policy",
        "Safety Policy",
        "Response Style",
    ]:
        assert heading in DEFAULT_JARVIS_MD


def test_repo_root_jarvis_md_exists() -> None:
    assert Path("JARVIS.md").exists()

