"""File snapshot/restore for checkpoint rollback."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any


class CheckpointSnapshotter:
    """Snapshots changed files at checkpoint time; can restore them on rollback."""

    def __init__(self, snapshot_dir: str | Path = ".jarvis/snapshots") -> None:
        self.snapshot_dir = Path(snapshot_dir).resolve()

    def snapshot_files(
        self, checkpoint_id: str, file_paths: list[str], workspace_root: str
    ) -> list[str]:
        """Copy each file_path to snapshot_dir/checkpoint_id/, preserving relative paths.
        Returns list of successfully snapshotted paths."""
        root = Path(workspace_root).resolve()
        dest_dir = self.snapshot_dir / checkpoint_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        saved: list[str] = []
        for rel in file_paths:
            src = (root / rel).resolve()
            if not src.exists() or not src.is_file():
                continue
            dest = dest_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            saved.append(rel)
        return saved

    def restore_files(
        self, checkpoint_id: str, workspace_root: str
    ) -> list[str]:
        """Copy snapshot files back to workspace. Returns list of restored paths."""
        root = Path(workspace_root).resolve()
        src_dir = self.snapshot_dir / checkpoint_id
        if not src_dir.exists():
            return []
        restored: list[str] = []
        for src in src_dir.rglob("*"):
            if not src.is_file():
                continue
            rel = src.relative_to(src_dir)
            dest = root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            restored.append(str(rel))
        return restored

    def list_snapshots(self) -> list[str]:
        """List all checkpoint IDs with stored snapshots."""
        if not self.snapshot_dir.exists():
            return []
        return sorted(
            p.name for p in self.snapshot_dir.iterdir() if p.is_dir()
        )

    def delete_snapshot(self, checkpoint_id: str) -> bool:
        """Remove snapshot directory. Returns True if deleted."""
        path = self.snapshot_dir / checkpoint_id
        if path.exists():
            shutil.rmtree(path)
            return True
        return False

    def snapshot_info(self, checkpoint_id: str) -> dict[str, Any]:
        """Return metadata about a snapshot."""
        path = self.snapshot_dir / checkpoint_id
        if not path.exists():
            return {"checkpoint_id": checkpoint_id, "exists": False, "files": []}
        files = [str(p.relative_to(path)) for p in path.rglob("*") if p.is_file()]
        return {
            "checkpoint_id": checkpoint_id,
            "exists": True,
            "files": files,
            "count": len(files),
        }
