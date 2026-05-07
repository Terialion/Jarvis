---
name: fix_test_failure
description: "Diagnose a failing test and propose a repair plan before editing code. Trigger when the user wants root-cause analysis for a failing test. Do NOT use to auto-edit files."
allowed-tools: Read,Bash
tags:
  - tests
  - diagnosis
version: 0.1
risk_level: write_approval_required
---

# When to use

- Use when a test is failing and the user wants help understanding the likely fix.

# Do NOT use

- Do not use to edit files automatically.
- Do not use when the user only wants a generic repo summary.

# Inputs

- Failing test command or error output
- Relevant source and test file paths

# Workflow

1. Reproduce or inspect the failing test output.
2. Read the relevant source and test files.
3. Explain the likely root cause.
4. Propose the smallest safe repair plan.

# Decision Rules

- If the failure is not reproducible, say so and base the plan on available logs only.
- Prefer minimal repair plans over broad refactors.

# Safety Rules

- Do not modify files without explicit approval.
- Do not expose secrets from test output or environment files.
- Respect shell approval boundaries.

# Output Format

- Failure summary
- Likely root cause
- Repair plan

# Failure Handling

- If the failing test cannot be located, say which identifiers were missing and what extra detail is needed.

# Examples

- Trigger: "Why is this pytest case failing?"
- Trigger: "Propose a fix plan for this failing test."
- Non-trigger: "Go ahead and rewrite the whole test suite."
