from __future__ import annotations

import difflib
from pathlib import Path

from ..store.redaction import redact_text_for_persistence


def unified_diff_for_replacement(path: Path, before: str, after: str, *, project_root: Path | None = None) -> str:
    label = str(path)
    if project_root is not None:
        try:
            label = str(path.resolve().relative_to(project_root.resolve())).replace("\\", "/")
        except Exception:
            label = path.name
    diff = "\n".join(
        difflib.unified_diff(
            before.splitlines(),
            after.splitlines(),
            fromfile=f"{label}:before",
            tofile=f"{label}:after",
            lineterm="",
        )
    )
    return redact_text_for_persistence(diff)
