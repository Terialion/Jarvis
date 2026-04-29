"""Shared endpoint constants for Web control UI and tests."""

API_ENDPOINTS = [
    "/api/health",
    "/api/capabilities",
    "/api/chat",
    "/api/tasks",
    "/api/approvals",
    "/api/settings/effective",
    "/api/gateway/status",
    "/api/channels",
    "/api/nodes",
    "/api/skills",
    "/api/logs",
    "/api/resources",
]

WS_ENDPOINTS = [
    "/ws/chat/{session_id}",
    "/ws/tasks/{task_id}",
    "/ws/terminal/{session_id}",
]
