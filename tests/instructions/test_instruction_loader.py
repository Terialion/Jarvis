from pathlib import Path

from src.jarvis.core.instructions import load_project_instructions


def test_instruction_loader_reads_project_agents_claude_and_override(tmp_path: Path) -> None:
    (tmp_path / "JARVIS.md").write_text("project guidance", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("agents guidance", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("claude guidance", encoding="utf-8")
    (tmp_path / ".jarvis").mkdir()
    (tmp_path / ".jarvis" / "JARVIS.override.md").write_text("override guidance", encoding="utf-8")

    bundle = load_project_instructions(tmp_path)
    scopes = [source.scope for source in bundle.sources if source.loaded]
    assert scopes[0] == "builtin"
    assert "project" in scopes
    assert "agents" in scopes
    assert "claude" in scopes
    assert scopes[-1] == "override"
    assert "override guidance" in bundle.combined_text


def test_instruction_loader_skips_sensitive_sources(tmp_path: Path) -> None:
    (tmp_path / ".jarvis").mkdir()
    (tmp_path / ".jarvis" / "JARVIS.override.md").write_text("ok", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=1", encoding="utf-8")
    bundle = load_project_instructions(tmp_path)
    assert ".env" not in bundle.combined_text

