"""Path traversal defense for generated scripts."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class PathViolation:
    """Single path safety issue."""
    path: str
    reason: str
    severity: str


_BLOCKED_TARGETS: list[str] = [
    "~/.bashrc", "~/.bash_profile", "~/.profile",
    "~/.ssh/", "~/.config/",
    "/etc/", "/usr/", "/bin/", "/sbin/",
    "/var/", "/root/", "/home/",
    "/dev/sd", "/dev/nv", "/dev/null",
    "/proc/", "/sys/",
]

_PATH_PATTERNS: list[str] = [
    r">{1,2}\s*([^\s;|&]+)",
    r"-[oO]\s+([^\s;|&]+)",
    r"--output[\s=]+([^\s;|&]+)",
    r"--outdir[\s=]+([^\s;|&]+)",
    r"--out[\s=]+([^\s;|&]+)",
]


class PathValidator:
    """Validate output paths in generated scripts."""

    def validate(self, script: str) -> list[PathViolation]:
        """Extract and validate all output paths."""
        violations: list[PathViolation] = []

        for pattern in _PATH_PATTERNS:
            for match in re.finditer(pattern, script):
                path = match.group(1).strip("'\"")
                v = self._check(path)
                if v:
                    violations.append(v)

        if "../" in script:
            violations.append(PathViolation("../", "Path traversal attempt", "critical"))

        return violations

    @staticmethod
    def _check(path: str) -> PathViolation | None:
        for blocked in _BLOCKED_TARGETS:
            if path.startswith(blocked) or blocked in path:
                return PathViolation(path, f"Blocked target: {blocked}", "critical")

        if path.startswith("~"):
            return PathViolation(path, "Home directory write not allowed", "critical")

        if path.startswith("/"):
            allowed = ("/tmp/biopipe_", "/scratch/")  # nosec B108
            if not any(path.startswith(a) for a in allowed):
                return PathViolation(path, "Absolute path outside allowed prefixes", "warning")

        return None
