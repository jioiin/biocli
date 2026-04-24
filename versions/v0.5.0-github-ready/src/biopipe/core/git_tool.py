"""Git tool: local-only git operations for provenance tracking.

Supports: init, add, commit, status, log, diff.
Does NOT support: push, pull, fetch, remote add. Those require network.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class GitResult:
    """Result of a git operation."""
    command: str
    stdout: str
    stderr: str
    success: bool


class GitTool:
    """Local-only git operations."""

    def __init__(self, workspace: Path | None = None) -> None:
        self._cwd = str(workspace or Path.cwd())

    def is_repo(self) -> bool:
        """Check if current directory is a git repo."""
        return self._run("git rev-parse --git-dir").success

    def init(self) -> GitResult:
        """Initialize a new git repo."""
        return self._run("git init")

    def status(self) -> GitResult:
        """Get git status."""
        return self._run("git status --short")

    def add(self, path: str = ".") -> GitResult:
        """Stage files."""
        return self._run(f"git add {path}")

    def commit(self, message: str) -> GitResult:
        """Commit with message."""
        try:
            result = subprocess.run(
                ["git", "commit", "-m", message],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=self._cwd,
            )
            return GitResult(
                command=f"git commit -m \"{message}\"",
                stdout=result.stdout.strip(),
                stderr=result.stderr.strip(),
                success=result.returncode == 0,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            return GitResult(
                command=f"git commit", stdout="", stderr=str(exc), success=False
            )

    def commit_script(self, script_path: str, pipeline_type: str, model: str) -> GitResult:
        """Commit a generated script with provenance metadata."""
        self.add(script_path)
        msg = f"biopipe: {pipeline_type} pipeline [model: {model}]"
        return self.commit(msg)

    def log(self, n: int = 10) -> GitResult:
        """Show recent commits."""
        return self._run(f"git log --oneline -n {n}")

    def diff(self, path: str | None = None) -> GitResult:
        """Show diff of changes."""
        cmd = f"git diff {path}" if path else "git diff"
        return self._run(cmd)

    def diff_staged(self) -> GitResult:
        """Show diff of staged changes."""
        return self._run("git diff --cached")

    def _run(self, command: str) -> GitResult:
        """Execute a git command locally."""
        # Block any network operations
        parts = command.split()
        if len(parts) > 1:
            blocked = {"push", "pull", "fetch", "clone", "remote"}
            if parts[1] in blocked:
                return GitResult(
                    command=command, stdout="", success=False,
                    stderr=f"'{parts[1]}' is blocked. BioPipe-CLI is local-only.",
                )

        try:
            result = subprocess.run(
                command.split(),
                capture_output=True,
                text=True,
                timeout=10,
                cwd=self._cwd,
            )
            return GitResult(
                command=command,
                stdout=result.stdout.strip(),
                stderr=result.stderr.strip(),
                success=result.returncode == 0,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            return GitResult(
                command=command, stdout="", stderr=str(exc), success=False
            )
