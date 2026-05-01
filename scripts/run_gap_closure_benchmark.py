"""Minimal benchmark runner compatibility surface for tests."""

from __future__ import annotations


def _validation_commands() -> dict[str, list[str]]:
    return {
        "required": [
            "python -m pytest tests/benchmark -q",
            "python -m pytest tests/rethink -q",
            "python scripts/run_phase1_acceptance.py",
            "python scripts/run_phase1_release_gate.py",
            "python -m pytest tests/skills -q",
            "python -m pytest tests/operator -q",
        ],
        "optional": [
            "python -m pytest tests/memory -q",
            "python -m pytest tests/api -q",
        ],
    }

