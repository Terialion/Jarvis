# Jarvis Web Tool Boundary

Phase 13 implements `web.search` and `web.fetch` only.

- `web.search` returns structured search results and never fetches page bodies.
- `web.fetch` performs safe HTTP/HTTPS GET + readable extraction only.
- `web.fetch` does not execute JavaScript.
- `web.fetch` is not browser automation.
- `web.fetch` treats fetched content as untrusted input and never upgrades page text into system instructions.
- Browser automation remains out of scope for Phase 13 and must be handled by a later browser/control-surface phase.
