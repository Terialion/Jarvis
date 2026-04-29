# Safe-use Mode

Safe-use mode is the default behavior for CLI and shared API.

## Default guardrails

- mode: `safe`
- max commands: `3`
- max files changed: `0`
- Docker: disabled
- external benchmark: disabled
- terminal command execution: disabled by default
- risky actions: approval required

## Task path

1. Create task in safe mode.
2. Emit policy and route events.
3. Push risky actions to approval queue.
4. Expose replay/evidence/operator summary.

## Approval flow

- `GET /api/approvals`
- `POST /api/approvals/{approval_id}/approve`
- `POST /api/approvals/{approval_id}/reject`

## Secret policy

CLI and API outputs must mask secret-like values.
Missing provider settings should raise warnings, not crash.
