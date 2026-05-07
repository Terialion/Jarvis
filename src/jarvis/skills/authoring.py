"""Skill authoring helpers for templates, creation, and report formatting."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from .schema import SkillSpec
from .validator import SkillValidationResult

DEFAULT_TEMPLATE = """---
name: {name}
description: "{description}"
allowed-tools: {allowed_tools}
tags:
  - {tag}
version: 0.1
---

# When to use

- Describe the trigger conditions for this skill.

# Do NOT use

- Describe when this skill should not be selected.

# Inputs

- List the expected inputs and assumptions.

# Workflow

1. Inspect the relevant inputs.
2. Perform only the bounded actions described by this skill.
3. Summarize the outcome and any uncertainty.

# Decision Rules

- State how to choose between branches or sub-modes.

# Safety Rules

- Do not reveal secrets.
- Do not execute scripts or install dependencies during validation.
- Respect approval and permission boundaries.

# Output Format

- Short summary
- Key findings or actions
- Next step

# Failure Handling

- Explain what to do if required files, tools, or inputs are missing.

# Examples

- Example request: "..."
- Example non-trigger: "..."
"""


def validate_skill_name(name: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_-]+", str(name or "").strip()))


def render_skill_template(
    name: str,
    *,
    description: str | None = None,
    allowed_tools: str = "Read",
    tag: str = "example",
) -> str:
    return DEFAULT_TEMPLATE.format(
        name=name,
        description=description or "One-line purpose with trigger and non-trigger boundaries.",
        allowed_tools=allowed_tools,
        tag=tag,
    )


def create_skill(
    name: str,
    *,
    base_dir: str | Path,
    description: str | None = None,
    allowed_tools: str = "Read",
    tag: str = "example",
) -> Path:
    if not validate_skill_name(name):
        raise ValueError("invalid skill name")
    skill_dir = Path(base_dir).resolve() / name
    skill_file = skill_dir / "SKILL.md"
    if skill_file.exists():
        raise FileExistsError(str(skill_file))
    skill_dir.mkdir(parents=True, exist_ok=False)
    skill_file.write_text(
        render_skill_template(name, description=description, allowed_tools=allowed_tools, tag=tag),
        encoding="utf-8",
    )
    return skill_file


def format_validation_result(result: SkillValidationResult) -> str:
    lines = [
        f"Skill validation: {result.skill_name}",
        f"Mode: {result.mode}",
        f"Status: {'OK' if result.ok else 'ERROR'}",
    ]
    errors = [finding for finding in result.findings if finding.level == "error"]
    warnings = [finding for finding in result.findings if finding.level == "warning"]
    if not errors:
        lines.append("No errors.")
    if warnings:
        lines.append("Warnings:")
        for finding in warnings:
            lines.append(f"- {finding.code}: {finding.message}")
    if errors:
        lines.append("Errors:")
        for finding in errors:
            lines.append(f"- {finding.code}: {finding.message}")
    return "\n".join(lines)


def format_skill_doctor(results: list[SkillValidationResult], specs: list[SkillSpec]) -> str:
    spec_map = {spec.name: spec for spec in specs}
    lines = ["## Skill Doctor Report", "", f"Scanned {len(results)} skills.", ""]
    lines.append("| # | Skill | Source | Mode | Result |")
    lines.append("|---|---|---|---|---|")
    ordered = sorted(
        results,
        key=lambda item: (
            0 if any(f.level == "error" for f in item.findings) else 1 if any(f.level == "warning" for f in item.findings) else 2,
            item.skill_name.lower(),
        ),
    )
    for idx, result in enumerate(ordered, start=1):
        if any(f.level == "error" for f in result.findings):
            marker = "[error]"
        elif any(f.level == "warning" for f in result.findings):
            marker = "[warning]"
        else:
            marker = "[ok]"
        source = spec_map.get(result.skill_name).source if spec_map.get(result.skill_name) else result.source
        lines.append(f"| {idx} | {result.skill_name} | {source} | {result.mode} | {marker} |")
    lines.extend(["", "## Details", ""])
    for result in ordered:
        issues = [finding for finding in result.findings if finding.level in {"error", "warning"}]
        if not issues:
            continue
        marker = "[error]" if any(f.level == "error" for f in issues) else "[warning]"
        lines.append(f"### {marker} {result.skill_name}")
        lines.append("")
        for finding in issues:
            lines.append(f"- [{finding.level}] {finding.code}: {finding.message}")
            if finding.recommendation:
                lines.append(f"  Recommendation: {finding.recommendation}")
        lines.append("")
    lines.append("> This report is based on static validation of current skill files.")
    return "\n".join(lines)


def format_skill_index(index_rows: list[dict[str, Any]]) -> str:
    lines = ["## Skill Index", ""]
    for row in index_rows:
        lines.append(f"- {row.get('name')}: {row.get('description')}")
        lines.append(f"  source={row.get('source')} risk={row.get('risk_level')} ({row.get('risk_level_source')})")
        lines.append(
            "  lifecycle="
            f"enabled:{row.get('enabled')} trust:{row.get('trust_status')} quarantine:{row.get('quarantined')}"
        )
        lines.append(f"  raw_allowed_tools={row.get('raw_allowed_tools')}")
        lines.append(f"  allowed_tools={', '.join(row.get('allowed_tools') or []) or 'none'}")
    return "\n".join(lines)
