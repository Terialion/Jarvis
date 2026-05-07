---
name: repo_overview
description: "Build a concise overview of the current repository from structure and top-level docs. Trigger when the user asks what the repo does or where to start. Do NOT use for file editing or test execution."
allowed-tools: Read
tags:
  - repo
  - overview
version: 0.1
risk_level: read_only
---

# When to use

- Use when the user asks for a repository overview, architecture summary, or suggested entry points.

# Do NOT use

- Do not use for modifying files.
- Do not use for running commands or tests.

# Inputs

- Current workspace path
- Top-level files such as `README.md`, `AGENTS.md`, or `JARVIS.md`

# Workflow

1. Inspect the repository structure.
2. Read the most relevant top-level project docs.
3. Summarize the project purpose, important folders, and likely entry points.

# Decision Rules

- If both `README.md` and `AGENTS.md` exist, use both and mention if they disagree.
- If top-level docs are missing, rely on file structure and say that documentation is limited.

# Safety Rules

- Do not reveal secrets or credentials from files.
- Stay read-only.

# Output Format

- One-paragraph overview
- Important folders or files
- Suggested next file to inspect

# Failure Handling

- If no useful docs are present, say so explicitly and fall back to structure-only summary.

# Examples

- Trigger: "What does this repo do?"
- Trigger: "Give me a quick repo overview."
- Non-trigger: "Run the tests."
