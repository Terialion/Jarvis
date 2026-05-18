from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _module_file(name: str) -> str | None:
    try:
        module = importlib.import_module(name)
    except Exception as exc:
        return f"ERROR: {type(exc).__name__}: {exc}"
    return str(getattr(module, "__file__", None))


def main() -> int:
    payload = {
        "jarvis.__file__": _module_file("jarvis"),
        "jarvis.cli.__file__": _module_file("jarvis.cli"),
        "src.jarvis.__file__": _module_file("src.jarvis"),
        "src.jarvis.core.routing.__file__": _module_file("src.jarvis.core.routing"),
        "src.jarvis.core.cli_response.__file__": _module_file("src.jarvis.core.cli_response"),
        "src.jarvis.core.repo_inspection.__file__": _module_file("src.jarvis.core.repo_inspection"),
        "src.jarvis.core.rethink.__file__": _module_file("src.jarvis.core.rethink"),
        "src.jarvis.core.react_readiness.__file__": _module_file("src.jarvis.core.react_readiness"),
        "sys.path_first_entries": sys.path[:5],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    ok = (
        str(payload["jarvis.cli.__file__"]).replace("\\", "/").endswith("/jarvis/cli.py")
        and "/src/jarvis/core/routing" in str(payload["src.jarvis.core.routing.__file__"]).replace("\\", "/")
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

