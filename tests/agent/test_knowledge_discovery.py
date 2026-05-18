"""Tests for s17: Knowledge auto-discovery — recursive SKILL.md scanning."""

from __future__ import annotations

from pathlib import Path

from src.jarvis.agent.context import ContextBuilder
from src.jarvis.agent.prompt_builder import PromptBuilder
from src.jarvis.agent.store import ThreadStore
from src.jarvis.agent.types import ChatInput
from src.jarvis.skills.registry import SkillRegistry


def test_nested_skills_under_skills_dir_discovered(tmp_path: Path):
    """Skills nested deeper than one level under skills/ should be discovered."""
    # Setup: skills/category/group/skill-name/SKILL.md
    skill_dir = tmp_path / "skills" / "devops" / "docker-tools"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("""---
name: docker-tools
description: Manage Docker containers and images.
risk_level: low
---
""")

    # Another flat skill for comparison
    flat_dir = tmp_path / "skills" / "web-search"
    flat_dir.mkdir(parents=True)
    (flat_dir / "SKILL.md").write_text("""---
name: web-search
description: Search the web.
risk_level: low
---
""")

    registry = SkillRegistry(project_root=tmp_path)
    names = registry.available_names()
    assert "docker-tools" in names
    assert "web-search" in names


def test_discovered_reference_skills_found(tmp_path: Path):
    """Skills in reference project subdirectories (*/skills/) should be discovered."""
    # Simulate learn-claude-code/skills/ structure
    ref_skill_dir = tmp_path / "learn-claude-code" / "skills" / "mcp-builder"
    ref_skill_dir.mkdir(parents=True)
    (ref_skill_dir / "SKILL.md").write_text("""---
name: mcp-builder
description: Build MCP servers.
risk_level: medium
---
""")

    registry = SkillRegistry(project_root=tmp_path, extra_dirs=[str(tmp_path / "learn-claude-code" / "skills")])
    names = registry.available_names()
    assert "mcp-builder" in names


def test_deeply_nested_skill_within_max_depth(tmp_path: Path):
    """Skills at depth 4-5 should still be discovered (MAX_DEPTH=6)."""
    # skills/a/b/c/d/skill-name/SKILL.md — 5 parts
    deep_dir = tmp_path / "skills" / "a" / "b" / "c" / "d" / "deep-skill"
    deep_dir.mkdir(parents=True)
    (deep_dir / "SKILL.md").write_text("""---
name: deep-skill
description: A deeply nested skill.
risk_level: low
---
""")

    registry = SkillRegistry(project_root=tmp_path)
    names = registry.available_names()
    assert "deep-skill" in names


def test_skills_in_skip_dirs_are_ignored(tmp_path: Path):
    """Skills in .git, node_modules, etc. should be skipped."""
    # Skill in .git should be ignored
    git_skill = tmp_path / "skills" / ".git" / "evil-skill"
    git_skill.mkdir(parents=True)
    (git_skill / "SKILL.md").write_text("""---
name: evil-skill
description: Should not be found.
---
""")

    # Skill in node_modules should be ignored
    nm_skill = tmp_path / "skills" / "node_modules" / "bad-pkg" / "skill"
    nm_skill.mkdir(parents=True)
    (nm_skill / "SKILL.md").write_text("""---
name: bad-skill
description: Should also be skipped.
---
""")

    # Normal skill should still be found
    good_dir = tmp_path / "skills" / "good-skill"
    good_dir.mkdir(parents=True)
    (good_dir / "SKILL.md").write_text("""---
name: good-skill
description: A valid skill.
risk_level: low
---
""")

    registry = SkillRegistry(project_root=tmp_path)
    names = registry.available_names()
    assert "good-skill" in names
    assert "evil-skill" not in names
    assert "bad-skill" not in names  # the node_modules one


def test_prompt_includes_discovered_skills(tmp_path: Path):
    """Discovered skills should appear in the prompt <skills> block."""
    skill_dir = tmp_path / "skills" / "my-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("""---
name: my-skill
description: Does useful things.
risk_level: low
allowed_tools:
  - read
  - search
---
""")

    store = ThreadStore(root=tmp_path / "threads")
    session = store.create_or_resume_session(ChatInput(text="help", cwd=str(tmp_path), project_id="p"))
    turn = store.create_turn(session["session_id"])
    turn_context = ContextBuilder(session_store=store, skill_registry=SkillRegistry(project_root=tmp_path)).build(
        session_id=session["session_id"],
        turn_id=turn.turn_id,
        chat_input=ChatInput(text="help", cwd=str(tmp_path), project_id="p"),
    )
    rendered = "\n".join(str(row.get("content") or "") for row in PromptBuilder().build_messages(turn_context))

    assert "<skills>" in rendered
    assert "my-skill" in rendered
    assert "Does useful things" in rendered
    assert "skill.load" in rendered
