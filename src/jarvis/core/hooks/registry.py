from __future__ import annotations

from collections import defaultdict
from typing import Any

from .models import HOOK_POINTS, HookRegistration


class HookRegistry:
    def __init__(self) -> None:
        self._hooks: dict[str, list[HookRegistration]] = defaultdict(list)

    def register(self, reg: HookRegistration) -> dict[str, Any]:
        if reg.hook_point not in HOOK_POINTS:
            return {"ok": False, "error": {"code": "HOOK_INVALID_POINT", "message": reg.hook_point}}
        self._hooks[reg.hook_point].append(reg)
        return {"ok": True, "data": {"hook_id": reg.hook_id, "hook_point": reg.hook_point}}

    def get(self, hook_point: str) -> list[HookRegistration]:
        return list(self._hooks.get(hook_point, []))

    def snapshot(self) -> dict[str, Any]:
        return {p: [h.hook_id for h in self._hooks.get(p, [])] for p in HOOK_POINTS}

