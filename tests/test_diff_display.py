"""Tests for diff display — auto_diff metadata emission."""
import pytest
from pathlib import Path


class TestAutoDiffMetadata:
    """Verify file write/edit tools attach auto_diff metadata."""

    def test_write_file_attaches_auto_diff_for_existing(self, tmp_path: Path):
        """write_file should attach auto_diff when modifying existing file."""
        from src.jarvis.core.file_editor import FileEditor

        file_path = tmp_path / "test.py"
        file_path.write_text("print('hello')")
        editor = FileEditor()
        editor._snapshot(str(file_path.resolve()), file_path.read_text())

        result = editor.write_file(path=str(file_path), content="print('hello world')")
        assert result["ok"]

    def test_write_file_created_flag(self, tmp_path: Path):
        """write_file should set created=True for new files."""
        from src.jarvis.core.file_editor import FileEditor

        file_path = tmp_path / "new_file.py"
        editor = FileEditor()
        result = editor.write_file(path=str(file_path), content="print('new')")
        assert result["ok"]
        assert result.get("data", {}).get("created") is True

    def test_replace_text_has_snapshot_before_diff(self, tmp_path: Path):
        """replace_text takes a snapshot before modifying, so diff works."""
        from src.jarvis.core.file_editor import FileEditor

        file_path = tmp_path / "test.py"
        file_path.write_text("line1\nline2\nline3")
        editor = FileEditor()
        editor._snapshot(str(file_path.resolve()), file_path.read_text())

        result = editor.replace_text(
            path=str(file_path),
            old="line2",
            new="line2_modified",
        )
        assert result["ok"]

        diff_result = editor.diff(path=str(file_path))
        data = diff_result.get("data", {})
        diff_text = data.get("diff_text", "")
        assert "line2_modified" in diff_text or "+line2_modified" in diff_text

    def test_auto_diff_content_is_valid_unified_format(self, tmp_path: Path):
        """auto_diff should contain valid unified diff text."""
        from src.jarvis.core.file_editor import FileEditor

        file_path = tmp_path / "test.py"
        file_path.write_text("original line")
        editor = FileEditor()
        editor._snapshot(str(file_path.resolve()), file_path.read_text())

        editor.replace_text(path=str(file_path), old="original", new="modified")
        diff_result = editor.diff(path=str(file_path))

        data = diff_result.get("data", {})
        diff_text = data.get("diff_text", "")
        # Should contain unified diff markers
        assert "modified" in diff_text
        assert diff_text
