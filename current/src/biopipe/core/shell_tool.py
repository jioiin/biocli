"""Shell tool: execute ONLY whitelisted read-only commands.

No arbitrary shell. Every command must be in the whitelist.
Output is captured and returned as string. Never piped to LLM raw.
"""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass


@dataclass
class ShellResult:
    """Result of a whitelisted shell command."""
    command: str
    stdout: str
    stderr: str
    exit_code: int
    allowed: bool


# Commands that are SAFE to run: read-only, no side effects
_WHITELIST: frozenset[str] = frozenset({
    # File listing
    "ls", "find", "tree", "du", "wc",
    # File reading (head only, not cat to prevent reading huge files)
    "head", "tail", "file",
    # Checksums
    "md5sum", "sha256sum",
    # System info
    "nproc", "free", "df", "uname", "hostname", "whoami",
    # Tool versions
    "which", "whereis", "type",
    # Bioinformatics read-only
    "samtools", "bcftools", "bedtools", "fastqc",
    # SLURM read-only (local commands on HPC)
    "squeue", "sinfo", "sacct", "scontrol",
    # Environment
    "module", "conda",
    # Git read-only
    "git",
})

# Subcommand prefixes that are allowed for multi-command tools.
# Rules are matched against tokens after the base command.
_SUBCOMMAND_WHITELIST: dict[str, frozenset[tuple[str, ...]]] = {
    "samtools": frozenset({
        ("--version",),
        ("view", "-c"),
        ("flagstat",),
        ("idxstats",),
        ("stats",),
    }),
    "bcftools": frozenset({("--version",), ("stats",), ("query",)}),
    "git": frozenset({("status",), ("log",), ("diff",), ("branch",), ("remote",), ("--version",)}),
    "conda": frozenset({("list",), ("info",), ("env", "list")}),
    "module": frozenset({("avail",), ("list",), ("spider",)}),
    "scontrol": frozenset({("show", "partition"), ("show", "node")}),
}

# Flags that are NEVER allowed regardless of command
_BLOCKED_FLAGS: frozenset[str] = frozenset({
    "-rf", "--force", "--delete", "--remove",
    "--exec", "-exec",
    "--output", "-o",  # no writing
})


class ShellTool:
    """Execute whitelisted shell commands safely."""

    def __init__(self, timeout: int = 10) -> None:
        self._timeout = timeout

    def run(self, command: str) -> ShellResult:
        """Run a command if it passes whitelist checks."""
        parts = shlex.split(command)
        if not parts:
            return ShellResult(command, "", "Empty command", -1, False)

        base_cmd = parts[0]

        # Gate 1: base command in whitelist
        if base_cmd not in _WHITELIST:
            return ShellResult(
                command, "", f"Command '{base_cmd}' not in whitelist", -1, False
            )

        # Gate 2: no blocked flags
        for flag in parts[1:]:
            if flag in _BLOCKED_FLAGS:
                return ShellResult(
                    command, "", f"Flag '{flag}' is blocked", -1, False
                )

        # Gate 3: subcommand check for multi-command tools
        if base_cmd in _SUBCOMMAND_WHITELIST and len(parts) > 1:
            cmd_tail = tuple(parts[1:])
            allowed_subs = _SUBCOMMAND_WHITELIST[base_cmd]
            if not any(
                len(cmd_tail) >= len(allowed_prefix)
                and cmd_tail[: len(allowed_prefix)] == allowed_prefix
                for allowed_prefix in allowed_subs
            ):
                return ShellResult(
                    command, "",
                    f"Subcommand '{base_cmd} {' '.join(parts[1:])}' not allowed. "
                    f"Allowed: {', '.join(' '.join(rule) for rule in sorted(allowed_subs))}",
                    -1, False
                )

        # Execute
        try:
            result = subprocess.run(
                parts,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                cwd=".",
            )
            return ShellResult(
                command=command,
                stdout=result.stdout[:10000],  # cap output
                stderr=result.stderr[:2000],
                exit_code=result.returncode,
                allowed=True,
            )
        except FileNotFoundError:
            return ShellResult(command, "", f"'{base_cmd}' not found on system", 127, True)
        except subprocess.TimeoutExpired:
            return ShellResult(command, "", f"Timed out after {self._timeout}s", -1, True)
