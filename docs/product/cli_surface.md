# CLI Surface

CLI is the primary and default local engineering interface.

## Commands

- `python -m jarvis.cli config`
- `python -m jarvis.cli tools`
- `python -m jarvis.cli server start --dry-run`
- `python -m jarvis.cli server status`
- `python -m jarvis.cli task run "Analyze this repo and suggest next steps."`
- `python -m jarvis.cli task status <task_id>`
- `python -m jarvis.cli task events <task_id>`
- `python -m jarvis.cli approvals list`
- `python -m jarvis.cli approvals approve <approval_id>`
- `python -m jarvis.cli approvals reject <approval_id>`
- `python -m jarvis.cli replay show <task_id>`
- `python -m jarvis.cli evidence show <task_id>`

## Safety

- Safe mode is the default task mode.
- Risky actions must remain approval-gated.
- Missing provider config must be warning-level, not crash.
- CLI must not print raw secrets.

## CLI Coding State Maintenance

- Inspect local coding state with `python -m jarvis.cli task state` or `/state`.
- Review pending approvals with `python -m jarvis.cli approvals list`.
- Run safe cleanup previews with `python -m jarvis.cli approvals prune --dry-run` and `python -m jarvis.cli task gc --dry-run`.
- Apply cleanup only with explicit confirmation via `--yes`.

