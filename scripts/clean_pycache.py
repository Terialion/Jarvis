#!/usr/bin/env python3
"""Clean Python cache files (__pycache__, .pyc, .pyo) from the project.

Usage:
    python scripts/clean_pycache.py [path] [--dry-run] [--include-venv]

By default, .venv/ is excluded to avoid breaking installed packages.
"""

import argparse
import shutil
import sys
from pathlib import Path


def find_pycache_dirs(root: Path) -> list[Path]:
    return sorted(root.rglob("__pycache__"))


def find_pyc_files(root: Path) -> list[Path]:
    return sorted(
        f for f in root.rglob("*.pyc") if f.parent.name != "__pycache__"
    )


def find_pyo_files(root: Path) -> list[Path]:
    return sorted(root.rglob("*.pyo"))


def _is_in_venv(path: Path) -> bool:
    return any(part == ".venv" for part in path.parts)


def clean(root: Path, dry_run: bool = False, include_venv: bool = False) -> dict:
    stats = {"__pycache__": 0, ".pyc": 0, ".pyo": 0}

    for d in find_pycache_dirs(root):
        if not include_venv and _is_in_venv(d):
            continue
        if dry_run:
            print(f"[DRY-RUN] would remove dir: {d}")
        else:
            shutil.rmtree(d)
            print(f"removed: {d}")
        stats["__pycache__"] += 1

    for pattern, key in [
        (find_pyc_files, ".pyc"),
        (find_pyo_files, ".pyo"),
    ]:
        for f in pattern(root):
            if not include_venv and _is_in_venv(f):
                continue
            if dry_run:
                print(f"[DRY-RUN] would remove file: {f}")
            else:
                f.unlink()
                print(f"removed: {f}")
            stats[key] += 1

    return stats


def main():
    parser = argparse.ArgumentParser(description="Clean Python cache files")
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Root directory to clean (default: current dir)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be removed without deleting",
    )
    parser.add_argument(
        "--include-venv",
        action="store_true",
        help="Also clean cache files inside .venv/ (default: excluded)",
    )
    args = parser.parse_args()

    root = Path(args.path).resolve()
    if not root.is_dir():
        print(f"Error: {root} is not a directory", file=sys.stderr)
        sys.exit(1)

    print(f"Scanning: {root}")
    stats = clean(root, dry_run=args.dry_run, include_venv=args.include_venv)
    total = sum(stats.values())
    if args.dry_run:
        print(f"\nWould remove {total} item(s): {stats}")
    else:
        print(f"\nRemoved {total} item(s): {stats}")


if __name__ == "__main__":
    main()