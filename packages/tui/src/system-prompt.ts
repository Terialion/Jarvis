export const REVIEW_PROMPT = `Review the uncommitted changes shown below. Focus on:
1. **Correctness** — logic errors, edge cases, off-by-one
2. **Security** — injection vectors, missing validation, leaked secrets
3. **Style** — consistency with surrounding code, naming

Be concise. Flag only real problems. Skip style nits that don't affect correctness.`;

export const SECURITY_REVIEW_PROMPT = `Audit the uncommitted changes shown below for security issues. Focus exclusively on:
1. **Injection** — SQL, command, shell, path traversal, template injection
2. **Secrets** — hardcoded keys, tokens, passwords, connection strings
3. **Input validation** — missing or bypassable checks, trust of user input
4. **Auth** — broken access control, missing authorization checks, session issues
5. **Crypto** — weak algorithms, broken nonce handling, timing attacks
6. **Data exposure** — logging sensitive data, error messages leaking internals

Be concise. Flag only real security problems. Not a general code review.`;

export const INIT_CLAUDE_MD_TEMPLATE = `# CLAUDE.md

This file provides instructions to AI coding assistants working in this project.

## Project Overview

<!-- Describe what this project does in 1-2 sentences -->

## Build & Test

\`\`\`bash
# Build
npm run build

# Test
npm test
\`\`\`

## Code Style

- Follow existing patterns in the codebase
- Write minimal code — no unnecessary abstractions
- Verify changes with tests before committing
`;
