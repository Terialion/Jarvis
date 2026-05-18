---
name: code_review
description: "Review code for bugs, security, style, and architecture concerns. Produce structured findings with severity ratings and suggestions. Trigger on 'review this code' or 'check for bugs'."
allowed-tools: Read
tags:
  - review
  - quality
  - security
  - bugs
version: 0.1
risk_level: read_only
---

# When to use

- Use when the user asks for a code review, bug check, or security audit.
- Use when the user says "review this", "check this code", or "find issues".
- Use when reviewing a specific file or a set of changed files.

# Do NOT use

- Do not use for editing the code — review only, do not modify files.
- Do not use for running tests or executing the code.
- Do not use for performance profiling or benchmarking.

# Inputs

- One or more file paths (required, can be inferred from git diff or user mention)
- Optional: specific concern areas (security, performance, style)

# Workflow

1. **Identify targets**: Determine which files to review from user input or `command_runner.run(command="git diff --name-only")`.
2. **Read each file**: Call `repo_reader.read_file(path="<path>")` for each target file.
3. **Check categories**:
   - **Correctness**: logic errors, off-by-one, null handling, edge cases.
   - **Security**: injection risks, hardcoded secrets, missing auth checks, unsafe deserialization.
   - **Style**: naming conventions, dead code, inconsistent patterns, missing error handling.
   - **Architecture**: tight coupling, missing abstractions, violation of existing patterns.
4. **Rate severity**: Critical / High / Medium / Low for each finding.
5. **Produce review**: Structured output with findings, severity, and actionable suggestions.

# Decision Rules

- If no files are specified, check git diff for changed files.
- Skip auto-generated files, vendored dependencies, and binary files.
- If a file is too long (>500 lines), review the most critical sections first.
- One finding per issue — do not bundle multiple problems into one item.

# Safety Rules

- Do not modify any files — review only.
- Do not expose secrets or credentials found in code.
- Flag hardcoded credentials as Critical severity.
- Do not execute or import the code being reviewed.

# Output Format

```
## Review: <file path(s)>

### Summary
1-2 sentence overview of overall quality and key concerns.

### Findings

| # | Severity | Category | Location | Issue | Suggestion |
|---|----------|----------|----------|-------|------------|
| 1 | Critical | Security | line X | ... | ... |
| 2 | Medium   | Style    | line Y | ... | ... |

### Recommendations
- Top 1-3 actionable improvements
```

# Failure Handling

- If a target file does not exist, note it and continue with remaining files.
- If git diff is empty, tell the user no changes were found to review.
- If the file type is unsupported (binary, image), skip with a note.

# Examples

- Trigger: "Review my recent changes."
- Trigger: "Code review src/jarvis/agent/loop.py."
- Trigger: "Check this code for bugs."
- Non-trigger: "Fix the bug in this file."
- Non-trigger: "Rewrite this module to be cleaner."
