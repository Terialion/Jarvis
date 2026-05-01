import sys
from pathlib import Path

# NOTE: tests/conftest.py handles path setup. This conftest is kept for
# backward compatibility but delegates to the root conftest.
_repo_root = Path(__file__).resolve().parents[2]
