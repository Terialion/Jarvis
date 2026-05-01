from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.jarvis.core.instructions import DEFAULT_JARVIS_MD


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a default JARVIS.md file.")
    parser.add_argument("workspace", nargs="?", default=".")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    target = Path(args.workspace).resolve() / "JARVIS.md"
    if target.exists() and not args.force:
        print(f"JARVIS.md already exists: {target}")
        return 0
    target.write_text(DEFAULT_JARVIS_MD, encoding="utf-8")
    print(f"Wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

