# Jarvis Skill Template

Jarvis skill templates use ecosystem-compatible frontmatter. External skills do not need to be rewritten, but Jarvis-authored skills should follow this structure so strict validation can stay predictable.

```md
---
name: my_skill
description: "One-line purpose with trigger and non-trigger boundaries."
allowed-tools: Read
tags:
  - example
version: 0.1
---

# When to use

- Describe the trigger conditions for this skill.

# Do NOT use

- Describe when this skill should not be selected.

# Inputs

- List required inputs and assumptions.

# Workflow

1. Outline the bounded steps.

# Decision Rules

- Explain how to choose between branches or sub-modes.

# Safety Rules

- Explain permission, secret, and boundary rules.

# Output Format

- Define the expected response structure.

# Failure Handling

- Explain what to do when inputs, files, or tools are missing.

# Examples

- Give at least one trigger and one non-trigger.
```

## Notes

- `allowed-tools` is preferred.
- `allowed_tools` is accepted as an alias.
- `risk_level` is optional and may be inferred.
- Full skill bodies are loaded only via `skill.load`.
- Validator never executes `scripts/`, `requirements.txt`, or `package.json`.
