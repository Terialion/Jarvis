import json
import subprocess
from pathlib import Path


ROOT = Path("d:/jarvis")
PY = ROOT / ".venv/Scripts/python.exe"


def test_swebench_lite_environment_check_script():
    completed = subprocess.run([str(PY), "scripts/prepare_swebench_lite.py", "--check-only"], cwd=str(ROOT), capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    path = ROOT / "temp/external_benchmarks/swebench_lite/environment_check.json"
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload.get("schema_version") == "jarvis.swebench_lite.environment.v1"
    assert "docker_available" in payload
    assert "dataset" in payload

