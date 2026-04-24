"""Team Collaboration Configuration: parse and manage shared BIOPIPE.md files.

BIOPIPE.md lives in the project root and enforces team standards:
genome, aligner, cluster queues, containers.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
import yaml


class TeamConfig:
    """Manages project-specific BIOPIPE.md configurations."""

    def __init__(self, cwd: str | Path | None = None):
        self._cwd = Path(cwd) if cwd else Path.cwd()
        self._config: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        """Load configuration from BIOPIPE.md or biopipe.yaml."""
        candidates = [
            self._cwd / "BIOPIPE.md",
            self._cwd / "biopipe.yaml",
            Path.home() / ".biopipe" / "config.yaml",
        ]

        for path in candidates:
            if path.exists():
                try:
                    if path.suffix in (".yaml", ".yml"):
                        with open(path, "r", encoding="utf-8") as f:
                            self._config = yaml.safe_load(f) or {}
                        break
                    elif path.name == "BIOPIPE.md":
                        self._config = self._extract_yaml_from_md(path)
                        break
                except Exception:
                    pass

    def _extract_yaml_from_md(self, path: Path) -> dict[str, Any]:
        """Extract YAML block from Markdown file."""
        content = path.read_text(encoding="utf-8", errors="replace")
        in_yaml = False
        yaml_lines = []

        for line in content.splitlines():
            if line.strip() == "```yaml":
                in_yaml = True
                continue
            if line.strip() == "```" and in_yaml:
                break
            if in_yaml:
                yaml_lines.append(line)

        if not yaml_lines:
            # Fallback to simple key: value parsing
            for line in content.splitlines():
                if ":" in line and not line.startswith("#"):
                    k, _, v = line.partition(":")
                    yaml_lines.append(f"{k.strip()}: {v.strip()}")

        try:
            return yaml.safe_load("\n".join(yaml_lines)) or {}
        except yaml.YAMLError:
            return {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)

    def to_context(self) -> str:
        """Format as LLM context."""
        if not self._config:
            return "No team configuration (BIOPIPE.md) found."

        lines = ["Team Configuration (BIOPIPE.md):"]
        for k, v in self._config.items():
            lines.append(f"  {k}: {v}")
        return "\n".join(lines)
