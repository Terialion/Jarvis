import sys
from pathlib import Path


_repo_root = Path(__file__).resolve().parents[2]
if str(_repo_root) in sys.path:
    sys.path.remove(str(_repo_root))
sys.path.insert(0, str(_repo_root))

