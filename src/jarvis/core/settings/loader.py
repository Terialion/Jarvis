from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class SettingsLoader:
    def load_json_file(self, path: str | Path | None) -> dict[str, Any]:
        if not path:
            return {}
        target = Path(path)
        if not target.exists():
            return {}
        return json.loads(target.read_text(encoding="utf-8"))

