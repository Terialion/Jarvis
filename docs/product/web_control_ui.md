# Web Control UI

Web Control UI is the primary graphical control surface.

## Location

- `web/control-ui/index.html`
- `web/control-ui/app.css`
- `web/control-ui/app.js`

## Sections

- Dashboard
- Task Console
- Approvals
- Replay
- Evidence
- Operator Summary
- Skills
- Channels
- Nodes
- Settings
- Logs
- Resources

## Data Source

UI must consume only shared API endpoints.

No direct runtime internals import is allowed in Web UI code.

## Start

1. Start API server:
   - `python -m jarvis.cli server start`
2. Open `web/control-ui/index.html` in a browser.
