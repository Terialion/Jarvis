import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import run_gap_closure_benchmark as runner


def test_required_optional_commands_shape():
    cmdset = runner._validation_commands()
    assert "required" in cmdset and "optional" in cmdset
    required = cmdset["required"]
    assert len(required) >= 6
    assert any("tests/benchmark -q" in c for c in required)
    assert any("tests/rethink -q" in c for c in required)
    assert any("run_phase1_acceptance.py" in c for c in required)
    assert any("run_phase1_release_gate.py" in c for c in required)
