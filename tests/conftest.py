import sys
from pathlib import Path

# Ensure src/ is in sys.path so jarvis.core imports work from any test directory.
_repo_root = Path(__file__).resolve().parents[1]  # tests/conftest.py -> tests/ -> D:\Jarvis
_src_dir = _repo_root / "src"
_src_str = str(_src_dir)
_root_str = str(_repo_root)

for p in [_root_str, _src_str]:
    while p in sys.path:
        sys.path.remove(p)

sys.path.insert(0, _src_str)
sys.path.insert(1, _root_str)

# Force-clear any cached jarvis from non-src location
if "jarvis" in sys.modules:
    _cached = sys.modules["jarvis"]
    if hasattr(_cached, "__file__") and _src_str not in str(getattr(_cached, "__file__", "")):
        to_remove = [k for k in sys.modules if k == "jarvis" or k.startswith("jarvis.")]
        for k in to_remove:
            del sys.modules[k]
