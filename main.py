#!/usr/bin/env python
"""Deprecated entrypoint compatibility shim."""

from __future__ import annotations

import argparse


def main() -> int:
    parser = argparse.ArgumentParser(prog="main.py", description="Deprecated entrypoint. Use `python -m jarvis.cli`.")
    parser.add_argument("--help-only", action="store_true", help="no-op flag for compatibility")
    parser.parse_args()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

