from __future__ import annotations

from typing import Any


def evaluate_skill_trust(manifest: dict[str, Any]) -> dict[str, Any]:
    permissions = list(manifest.get("permissions") or [])
    trust_level = str(manifest.get("trust_level") or "untrusted")
    broad = any(p in {"filesystem.write_all", "shell.exec_all", "network.unrestricted"} for p in permissions)
    quarantined = broad or trust_level in {"untrusted", "unknown"}
    return {
        "ok": True,
        "data": {
            "quarantined": quarantined,
            "trust_level": trust_level,
            "reason": "broad_permissions" if broad else ("low_trust" if quarantined else "trusted"),
        },
    }

