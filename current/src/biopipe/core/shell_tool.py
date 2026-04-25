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

# Subcommands that are allowed for multi-command tools
_SUBCOMMAND_WHITELIST: dict[str, frozenset[str]] = {
    "samtools": frozenset({"--version", "flagstat", "idxstats", "stats", "view -c"}),
    "bcftools": frozenset({"--version", "stats", "query"}),
    "git": frozenset({"status", "log", "diff", "branch", "remote", "--version"}),
    "conda": frozenset({"list", "info", "env list"}),
    "module": frozenset({"avail", "list", "spider"}),
    "scontrol": frozenset({"show partition", "show node"}),
}

# Flags that are NEVER allowed regardless of command
_BLOCKED_FLAGS: frozenset[str] = frozenset({
    "-rf", "--force", "--delete", "--remove", "-delete", "-ok", "-okdir",
    "--exec", "-exec",
    "--output", "-o",  # no writing
})

# find-specific hardening: allow only read-only search primitives
_FIND_BLOCKED_ACTION_PRIMARIES: frozenset[str] = frozenset({
    "-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprint0", "-fprintf",
})
_FIND_ALLOWED_OPERATORS: frozenset[str] = frozenset({"(", ")", "!", "-a", "-o", ","})
_FIND_ALLOWED_OPTIONS_NOARG: frozenset[str] = frozenset({"-L", "-H", "-P", "-xdev", "-mount", "-noleaf"})
_FIND_ALLOWED_OPTIONS_WITH_ARG: frozenset[str] = frozenset({"-maxdepth", "-mindepth"})
_FIND_ALLOWED_PRIMARIES_NOARG: frozenset[str] = frozenset({
    "-empty", "-readable", "-writable", "-executable", "-true", "-false", "-print", "-print0", "-ls",
    "-prune", "-quit",
})
_FIND_ALLOWED_PRIMARIES_WITH_ARG: frozenset[str] = frozenset({
    "-name", "-iname", "-path", "-ipath", "-regex", "-iregex", "-type", "-size", "-mtime", "-mmin",
    "-ctime", "-cmin", "-atime", "-amin", "-newer", "-user", "-group", "-perm", "-links", "-inum",
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

        # Gate 2b: find-specific action-primary + allowlist validation
        if base_cmd == "find":
            find_validation = self._validate_find_expression(parts)
            if find_validation is not None:
                return ShellResult(command, "", find_validation, -1, False)

        # Gate 3: subcommand check for multi-command tools
        if base_cmd in _SUBCOMMAND_WHITELIST and len(parts) > 1:
            subcmd = parts[1]
            allowed_subs = _SUBCOMMAND_WHITELIST[base_cmd]
            if subcmd not in allowed_subs and not subcmd.startswith("--version"):
                return ShellResult(
                    command, "",
                    f"Subcommand '{base_cmd} {subcmd}' not allowed. "
                    f"Allowed: {', '.join(sorted(allowed_subs))}",
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

    def _validate_find_expression(self, parts: list[str]) -> str | None:
        """Validate `find` expression as read-only and allowlisted."""
        expect_value_for: str | None = None

        for token in parts[1:]:
            if token in _FIND_BLOCKED_ACTION_PRIMARIES:
                return f"find action primary '{token}' is blocked"

            if expect_value_for is not None:
                expect_value_for = None
                continue

            if token in _FIND_ALLOWED_OPERATORS or token in _FIND_ALLOWED_OPTIONS_NOARG:
                continue

            if token in _FIND_ALLOWED_OPTIONS_WITH_ARG or token in _FIND_ALLOWED_PRIMARIES_WITH_ARG:
                expect_value_for = token
                continue

            if token in _FIND_ALLOWED_PRIMARIES_NOARG:
                continue

            if token.startswith("-"):
                return f"find token '{token}' is not in allowlist"

        if expect_value_for is not None:
            return f"find token '{expect_value_for}' requires a value"

        return None
