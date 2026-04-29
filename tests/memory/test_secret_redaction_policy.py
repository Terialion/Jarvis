import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from jarvis.core.memory.write_policy import sanitize_memory_value


def test_secret_like_values_rejected_or_redacted():
    ok, value = sanitize_memory_value("api_key=abcdef123456")
    assert ok is False
    assert "REDACTED" in value
