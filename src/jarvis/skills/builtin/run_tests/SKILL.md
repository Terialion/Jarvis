---
name: run_tests
description: "Run project tests and summarize results without hiding failures. Trigger when the user asks to run tests or verify a change. Do NOT use for code edits."
allowed-tools: Bash,Read
tags:
  - tests
  - verification
version: 0.1
risk_level: command
---

# When to use

- Use when the user asks to run tests, verify a change, or inspect failing test output.

# Do NOT use

- Do not use for unrelated repository summaries.
- Do not claim success without test output.

# Inputs

- The requested test scope or command
- Current workspace path

# Workflow

1. Choose the narrowest useful test scope.
2. Run the test command.
3. Summarize pass or fail results honestly.

# Decision Rules

- Prefer scoped tests over broad suites when the user points to a file or feature.
- If the user explicitly asks for the full suite, honor that.

# Safety Rules

- Do not hide failing tests.
- Respect shell approval and permission boundaries.

# Output Format

- Command run
- Result summary
- Key failures or warnings

# Failure Handling

- If the command cannot run, report the blocking error and suggest the next smallest viable test command.

# Examples

- Trigger: "Run pytest for this package."
- Trigger: "Verify the latest fix."
- Non-trigger: "Edit the failing test for me."
