from __future__ import annotations

from src.jarvis.skills.authoring import render_skill_template


def test_skill_authoring_template_has_required_sections():
    text = render_skill_template("my_skill")
    assert "allowed-tools: Read" in text
    for section in (
        "# When to use",
        "# Do NOT use",
        "# Inputs",
        "# Workflow",
        "# Decision Rules",
        "# Safety Rules",
        "# Output Format",
        "# Failure Handling",
        "# Examples",
    ):
        assert section in text

