from pathlib import Path

from src.jarvis.core.repo_inspection import RepoInspectionRequest, inspect_repo
from src.jarvis.core.repo_inspection.workspace import ensure_within_workspace


def test_sensitive_paths_are_skipped(tmp_path: Path):
    (tmp_path / "README.md").write_text("demo", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=1", encoding="utf-8")
    ssh = tmp_path / ".ssh"
    ssh.mkdir()
    (ssh / "id_rsa").write_text("PRIVATE", encoding="utf-8")
    (tmp_path / "secret.key").write_text("PRIVATE", encoding="utf-8")
    result = inspect_repo(RepoInspectionRequest(workspace_root=tmp_path, user_input="inspect"))
    skipped = {(s.path, s.reason) for s in result.files_skipped}
    assert any(".env" in p and r == "sensitive" for p, r in skipped)
    assert "Sensitive path denylist was enforced." in result.safety_notes


def test_ignored_dirs_are_not_recursed(tmp_path: Path):
    (tmp_path / "README.md").write_text("demo", encoding="utf-8")
    nm = tmp_path / "node_modules"
    nm.mkdir()
    (nm / "a.js").write_text("console.log(1)", encoding="utf-8")
    result = inspect_repo(RepoInspectionRequest(workspace_root=tmp_path, user_input="inspect"))
    all_considered = "\n".join(result.files_considered)
    assert "node_modules/a.js" not in all_considered


def test_workspace_boundary_rejects_outside_path(tmp_path: Path):
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("x", encoding="utf-8")
    try:
        ensure_within_workspace(outside, tmp_path)
        assert False, "expected ValueError"
    except ValueError:
        pass
