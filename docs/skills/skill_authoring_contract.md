# Jarvis Skill Authoring Contract

Jarvis supports ecosystem-compatible `SKILL.md` files. Imported skills do not need to be rewritten into a Jarvis-only format before they can be scanned, indexed, or loaded.

## Compatibility Rules

- `allowed-tools` is the preferred external ecosystem field.
- `allowed_tools` is accepted as a Jarvis internal alias.
- `risk_level` is optional for external skills and may be inferred.
- `alwaysApply` and `always_apply` are both accepted.
- `read_when` is accepted when present.
- `_meta.json` and `_skillhub_meta.json` are accepted as sidecar metadata sources.

## Validation Modes

- `strict`
  - Use for Jarvis-authored builtin skills and user-created Jarvis skills.
  - Requires the full authoring contract sections and normalized tool declarations.
- `compatibility`
  - Use for imported marketplace, SkillHub, Claude Code, OpenClaw, or CodeBuddy style skills.
  - Allows incomplete ecosystem metadata and reports warnings instead of forcing rewrites.

## Runtime Boundary

- Full skill bodies are loaded only through `skill.load`.
- PromptBuilder injects skill metadata only, not every full skill body.
- The validator never executes skill code or scripts.
- Executable skill runtime belongs to Phase 10B, not Phase 10A.

## Required Sections For Jarvis-Authored Skills

- When to use
- Do NOT use
- Inputs
- Workflow
- Decision Rules
- Safety Rules
- Output Format
- Failure Handling
- Examples

## Tool Declaration Guidance

- Use ecosystem-compatible `allowed-tools`.
- Prefer broad ecosystem declarations like `Read`, `Write`, or `Bash` for portability.
- Jarvis will normalize these into internal capabilities during loading.

## Safety Expectations

- Skills must not embed real secrets, tokens, or credentials.
- Skills with command, write, network, or credentialed behavior must explain Safety Rules.
- Validator output is static analysis only and does not imply runtime permission bypass.
