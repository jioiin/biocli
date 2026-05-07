"""Security tests for file_read tool path restrictions."""

from __future__ import annotations

import asyncio
from pathlib import Path

from biopipe.tools.file_read import ACCESS_DENIED_ERROR, FileReadTool


class TestFileReadToolSecurity:
    def test_allowed_file_inside_workspace(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        target = tmp_path / "notes.txt"
        target.write_text("hello workspace")

        result = asyncio.run(FileReadTool().execute(path=str(target)))

        assert "ERROR:" not in result
        assert "hello workspace" in result

    def test_denied_absolute_system_path(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)

        result = asyncio.run(FileReadTool().execute(path="/etc/hosts"))

        assert result == f"ERROR: {ACCESS_DENIED_ERROR}"

    def test_denied_parent_traversal(self, tmp_path: Path, monkeypatch) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (tmp_path / "secret.txt").write_text("top secret")
        monkeypatch.chdir(workspace)

        result = asyncio.run(FileReadTool().execute(path="../secret.txt"))

        assert result == f"ERROR: {ACCESS_DENIED_ERROR}"
