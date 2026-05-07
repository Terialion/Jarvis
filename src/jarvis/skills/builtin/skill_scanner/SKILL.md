---
name: skill_scanner
description: "Validate or audit Jarvis and ecosystem skill files for structure, permission, and security risks before use. Triggers on: skill safety, skill validation, skill doctor, audit skill, scan skill. Do NOT trigger for normal coding tasks."
allowed-tools: Read
tags:
  - skill
  - security
  - validation
version: 0.1
---

# Security Declaration

- This skill performs local static analysis only.
- It never executes skill scripts, installs dependencies, or sends file contents externally.

# When to use

- Use when the user wants to validate, audit, scan, or review one or more skill files.

# Do NOT use

- Do not use for normal coding tasks.
- Do not use as a replacement for runtime execution or sandbox enforcement.

# Inputs

- One skill name, one skill path, or a set of discovered skill directories.
- Requested validation mode: compatibility or strict.

# Workflow

1. Locate the relevant `SKILL.md` and sidecar metadata files.
2. Parse frontmatter and normalize ecosystem fields.
3. Apply static validation rules without executing code.
4. Report findings with stable severity and recommendations.

# Decision Rules

- Use strict mode for Jarvis-authored builtin or user-created skills.
- Use compatibility mode for imported or marketplace-style skills.

# Safety Rules

- Perform local static analysis only.
- Do not execute skill scripts, package hooks, or command examples.
- Do not install dependencies.
- Do not send skill contents, credentials, or file excerpts to external services.
- Report validator findings exactly as observed instead of improvising remediation steps.

# Local Validation Rules

- Check required metadata fields.
- Check allowed-tools normalization and risk inference.
- Check required sections and Safety Rules for risky skills.
- Check for hardcoded secrets and prompt override indicators.

# Risk Levels

- `read_only`
- `write_approval_required`
- `command`
- `network`
- `credentialed`
- `unknown`

# Output Format

- Validation status
- Errors
- Warnings
- Recommendations

# Failure Handling

- If a skill cannot be parsed, report the parse error and stop before any execution.
- If metadata is incomplete, report warnings or errors according to validation mode.

# Examples

- Trigger: "Run skill doctor."
- Trigger: "Validate summarize_file."
- Non-trigger: "Use this skill to change files for me."
