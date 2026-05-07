---
name: summarize_file
description: "Summarize a specific file by reading it and extracting key points. Trigger when the user asks to explain or summarize one file. Do NOT use for editing."
allowed-tools: Read
tags:
  - file
  - summary
version: 0.1
risk_level: read_only
---

# When to use

- Use when the user asks to summarize, explain, or inspect a specific file.

# Do NOT use

- Do not use for file edits.
- Do not use when the user has not identified which file they mean.

# Inputs

- A file path or a clear file reference

# Workflow

1. Confirm the target file path.
2. Read the file.
3. Summarize the file purpose, main logic, and notable details.

# Decision Rules

- If the path is ambiguous, ask for clarification before proceeding.
- If the file is very long, summarize the most relevant sections first.

# Safety Rules

- Do not reveal secrets or credentials.
- Stay read-only.

# Output Format

- Short summary
- Key points
- Relevant file path

# Failure Handling

- If the file is missing or unreadable, say so and suggest the next closest file to inspect.

# Examples

- Trigger: "Summarize README.md."
- Trigger: "Explain src/jarvis/agent/loop.py."
- Non-trigger: "Replace text in README.md."
