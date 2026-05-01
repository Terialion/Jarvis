from pathlib import Path

from src.jarvis.core.repo_inspection import RepoInspectionRequest, inspect_repo


def test_basic_python_project_inspection(tmp_path: Path):
    (tmp_path / "README.md").write_text("# Demo", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    src = tmp_path / "src" / "demo"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("", encoding="utf-8")
    (src / "cli.py").write_text("def main():\n    pass\n", encoding="utf-8")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_demo.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    result = inspect_repo(RepoInspectionRequest(workspace_root=tmp_path, user_input="inspect"))
    assert "python" in result.project_type
    assert any("README.md" in r.path for r in result.files_read)
    assert any("pyproject.toml" in r.path for r in result.files_read)
    assert any("cli.py" in p for p in result.entrypoints)
    assert "tests" in result.test_layout


def test_huge_and_binary_files_skipped(tmp_path: Path):
    (tmp_path / "README.md").write_text("demo", encoding="utf-8")
    huge = tmp_path / "huge.txt"
    huge.write_text("x" * 70000, encoding="utf-8")
    binary = tmp_path / "bin.dat"
    binary.write_bytes(b"\x00\x01\x02\x03")
    result = inspect_repo(RepoInspectionRequest(workspace_root=tmp_path, user_input="inspect"))
    skipped = {(Path(s.path).name, s.reason) for s in result.files_skipped}
    assert ("huge.txt", "too_large") in skipped or ("huge.txt", "limit") in skipped
    assert ("bin.dat", "binary") in skipped or ("bin.dat", "decode_error") in skipped
