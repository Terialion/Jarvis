# Deprecated Desktop App

Desktop app support is deprecated.

Current product surfaces:
- CLI is the primary local execution interface.
- Web Control UI is the primary graphical interface.

Legacy desktop reference:
- `legacy/desktop/jarvis_desktop_app.py`
- `legacy/desktop/README.md`

Rules:
- Do not add new desktop features.
- Do not import desktop app from runtime code paths.
- Keep legacy copy only for audit and rollback reference.
