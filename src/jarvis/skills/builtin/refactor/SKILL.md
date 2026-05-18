---
name: refactor
description: "Analyze code for improvement and apply changes incrementally without altering behavior. Focus on readability, maintainability, and structure. Trigger on 'refactor', 'clean up', or 'simplify'."
allowed-tools: Read, Bash
tags:
  - refactoring
  - cleanup
  - improvement
version: 0.1
risk_level: write_approval_required
---

# When to use

- Use when the user asks to refactor, clean up, simplify, or improve existing code.
- Use when the goal is better structure, readability, or maintainability.
- Use when removing duplication, extracting helpers, or improving naming.

# Do NOT use

- Do not use for fixing bugs (use the fix_bug skill instead).
- Do not use for adding new features or changing behavior.
- Do not use for performance optimization unless specifically requested.
- Do not use for rewriting from scratch — preserve the existing design intent.

# Inputs

- Target file(s) or module(s) to refactor (required)
- Optional: specific concern (readability, DRY, naming, structure)

# Workflow

1. **Read and understand**: Call `repo_reader.read_file` for each target file. Understand the current design and behavior.
2. **Identify issues**: List specific problems with rationale — long functions, duplicated code, unclear names, deep nesting, mixed concerns.
3. **Plan changes**: Break the refactor into small, independent, reversible steps. Each step should be safe to apply alone.
4. **Present plan**: Show the planned changes and get user approval before editing.
5. **Apply incrementally**: Make one change at a time, verify each step.
6. **Verify**: Run existing tests after each change. Confirm behavior is unchanged.

# Decision Rules

- Preserve external behavior — refactoring must not change what the code does.
- Keep public APIs stable unless the user explicitly approves changes.
- Prefer extracting helper functions over adding comments.
- Each step must be independently reversible.
- If a change would break tests, flag it and get approval before proceeding.

# Safety Rules

- Ask for approval before any file modification.
- Run existing tests after each change to catch regressions.
- Do not change public interfaces or APIs without explicit permission.
- Do not refactor test files alongside source files — keep changes focused.
- Do not delete code unless you are certain it is dead.

# Output Format

```
## Issues Identified

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| 1 | ...   | file:line | ...    |

## Planned Changes

### Step 1: <description>
- File: `...`
- Change: <brief description>
- Risk: Low/Medium

### Step 2: ...

## Applied (after each step)
<diff of actual changes>
```

# Failure Handling

- If tests fail after a change, revert that step and diagnose before retrying.
- If a target file is too complex for safe refactoring, say so and suggest smaller steps.
- If the user rejects the plan, revise based on feedback before touching code.

# Examples

- Trigger: "Refactor src/jarvis/agent/loop.py — it's getting too long."
- Trigger: "Clean up this function — too much duplication."
- Trigger: "简化这段代码，让它更易读。"
- Non-trigger: "Fix the null pointer bug."
- Non-trigger: "Add a caching layer to improve performance."
