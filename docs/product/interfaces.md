# Product Interfaces

Jarvis product interfaces are split into two surfaces:

1. CLI (local execution surface)
2. Web Control UI (graphical control surface)

Desktop app is deprecated and preserved only in `legacy/desktop`.

## Shared API

Core endpoints:
- `GET /api/health`
- `GET /api/capabilities`
- `POST /api/tasks`
- `GET /api/tasks/{task_id}`
- `GET /api/tasks/{task_id}/events`
- `GET /api/tasks/{task_id}/replay`
- `GET /api/tasks/{task_id}/evidence`
- `GET /api/tasks/{task_id}/operator-summary`
- `GET /api/approvals`
- `POST /api/approvals/{approval_id}/approve`
- `POST /api/approvals/{approval_id}/reject`
- `GET /api/settings/effective`

Read-only control endpoints:
- `GET /api/gateway/status`
- `GET /api/channels`
- `GET /api/nodes`
- `GET /api/skills`
- `GET /api/logs`
- `GET /api/resources`
