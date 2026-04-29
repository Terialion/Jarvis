# React Chat UI Direction

Jarvis Web UI starts as a React messaging surface with streaming event support.

## Phase 1

- React chat session list
- message composer
- assistant stream area
- tool and approval event cards
- safe mode indicator

## Streaming

Preferred transport:
- WebSocket channels (`/ws/chat/{session_id}`, `/ws/tasks/{task_id}`, `/ws/terminal/{session_id}`)

Fallback transport:
- polling/SSE style event endpoints

## OpenClaw-style expansion

After chat baseline, expand to control pages:
- task console
- terminal
- approvals
- replay
- evidence
- operator summary
- skills/channels/nodes/logs/resources

This keeps a messaging-first flow while evolving toward an OpenClaw-style control surface.
