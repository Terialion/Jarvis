# Shared API

Jarvis uses a shared API layer so CLI and Web UI consume the same control surface.

## Core endpoints

- `GET /api/health`
- `GET /api/capabilities`
- `GET /api/settings/effective`

## Chat and tasks

- `POST /api/chat`
- `GET /api/chat/{session_id}`
- `GET /api/chat/{session_id}/messages`
- `GET /api/chat/{session_id}/events`
- `POST /api/tasks`
- `GET /api/tasks/{task_id}`
- `GET /api/tasks/{task_id}/events`
- `GET /api/tasks/{task_id}/replay`
- `GET /api/tasks/{task_id}/evidence`
- `GET /api/tasks/{task_id}/operator-summary`

## Terminal bridge

- `POST /api/terminal/sessions`
- `GET /api/terminal/sessions/{session_id}`
- `GET /api/terminal/sessions/{session_id}/events`
- `POST /api/terminal/sessions/{session_id}/input`

Terminal input is blocked by default in safe mode.

## Approval and control endpoints

- `GET /api/approvals`
- `POST /api/approvals/{approval_id}/approve`
- `POST /api/approvals/{approval_id}/reject`
- `GET /api/gateway/status`
- `GET /api/channels`
- `GET /api/nodes`
- `GET /api/skills`
- `GET /api/logs`
- `GET /api/resources`

## Start server

- `python -m jarvis.cli server start`
- `python -m jarvis.cli server status`
