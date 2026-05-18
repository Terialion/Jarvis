---
name: fix_bug
description: "Diagnose a bug by reproducing the failure, tracing root cause, proposing a minimal fix, and applying it with approval. Trigger on 'fix this bug', 'debug this error', or 'why is this broken'."
allowed-tools: Read, Bash
tags:
  - debugging
  - fix
  - diagnosis
version: 0.1
risk_level: write_approval_required
---

# When to use

- Use when the user reports a bug, error, crash, or unexpected behavior.
- Use when the user provides an error message, stack trace, or failing test output.
- Use when the user says "fix this", "debug", or "why is this broken".

# Do NOT use

- Do not use for new feature development or enhancements.
- Do not use for general code refactoring (use the refactor skill instead).
- Do not use for writing new tests (unless needed to verify the fix).
- Do not use for performance optimization (use standard tools).

# Inputs

- Error message, stack trace, or description of broken behavior (required)
- Optional: relevant file paths, steps to reproduce, expected vs actual behavior

# Workflow

1. **Reproduce**: Read any error output, stack traces, or test failures. Run the failing command if safe and available.
2. **Trace**: Read the relevant source files around the error location. Follow the call chain backward to find the root cause.
3. **Diagnose**: Identify the specific line(s) and logic that cause the bug. Explain WHY it's wrong, not just WHERE.
4. **Propose**: Design the smallest possible fix. Prefer surgical changes over broad refactors.
5. **Get approval**: Present the diagnosis and proposed fix. Ask for confirmation before editing.
6. **Apply**: Use `file_editor.replace_text` to apply the fix.
7. **Verify**: Re-run the failing test or reproduce scenario to confirm the fix works.

# Decision Rules

- Fix root causes, not symptoms. Trace back until you find the origin.
- One bug at a time. Do not fix multiple unrelated bugs in one pass.
- If the root cause is in a dependency, explain it and suggest workarounds.
- If you cannot reproduce, say so and work from available information.
- Do not change code until the user approves the proposed fix.

# Safety Rules

- Always ask for approval before editing files.
- Do not modify test files unless the bug is IN the test.
- Do not change public APIs or interfaces without explicit permission.
- Do not expose secrets or credentials in error output.
- Keep the fix minimal — do not refactor surrounding code.

# Output Format

```
## Diagnosis

**Root cause**: <1-2 sentence explanation>

**Location**: `<file>:<line>` — <what the code does vs what it should do>

## Proposed Fix

<code diff or description of the change>

## Verification

<steps to confirm the fix works>
```

# Failure Handling

- If the error message is incomplete, ask the user for the full stack trace.
- If the bug cannot be reproduced, list what was tried and ask for more context.
- If the fix introduces new issues, revert and re-diagnose.
- If the bug is in generated/vendored code, suggest upstream fix or workaround.

# Examples

- Trigger: "I'm getting a TypeError on line 42, can you fix it?"
- Trigger: "This test is failing — debug and fix it."
- Trigger: "帮我修这个 bug: 点击按钮后页面崩溃"
- Non-trigger: "Add a new feature for user authentication."
- Non-trigger: "Refactor this whole module."
