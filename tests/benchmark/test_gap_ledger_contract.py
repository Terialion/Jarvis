import json
from pathlib import Path

from jsonschema import Draft202012Validator


def test_gap_ledger_matches_schema() -> None:
    root = Path("d:/jarvis")
    schema = json.loads((root / "docs/schemas/benchmarks/gap_ledger.schema.json").read_text(encoding="utf-8"))
    ledger = json.loads((root / "docs/benchmarks/gap_ledger.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(ledger), key=lambda e: list(e.path))
    assert not errors, "; ".join(f"{'/'.join(map(str, e.path))}: {e.message}" for e in errors)

