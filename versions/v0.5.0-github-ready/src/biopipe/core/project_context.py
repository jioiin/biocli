"""BIOPIPE.md reader: project context file.

Like CLAUDE.md for Claude Code or GEMINI.md for Gemini CLI.
Scientist describes their project once, agent reads at every start.

Example BIOPIPE.md:
    # Project: Mouse Liver RNA-seq
    organism: Mus musculus
    genome: mm39
    sequencing: paired-end Illumina NovaSeq
    cluster: Stanford Sherlock (SLURM)
    partition: normal
    adapters: TruSeq
    conventions:
      - All output in ./results/{sample}/
      - Always use fastp, not trimmomatic
      - STAR aligner preferred over HISAT2
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ProjectContext:
    """Parsed BIOPIPE.md project context."""
    raw_text: str = ""
    organism: str | None = None
    genome: str | None = None
    sequencing: str | None = None
    cluster: str | None = None
    partition: str | None = None
    adapters: str | None = None
    conventions: list[str] = field(default_factory=list)
    extra: dict[str, str] = field(default_factory=dict)

    def format_for_llm(self) -> str:
        """Format as LLM context injection."""
        if not self.raw_text:
            return ""
        parts = ["<project_context>"]
        if self.organism:
            parts.append(f"Organism: {self.organism}")
        if self.genome:
            parts.append(f"Reference genome: {self.genome}")
        if self.sequencing:
            parts.append(f"Sequencing: {self.sequencing}")
        if self.cluster:
            parts.append(f"Cluster: {self.cluster}")
        if self.partition:
            parts.append(f"Partition: {self.partition}")
        if self.adapters:
            parts.append(f"Adapters: {self.adapters}")
        if self.conventions:
            parts.append("Conventions:")
            for c in self.conventions:
                parts.append(f"  - {c}")
        parts.append("</project_context>")
        return "\n".join(parts)

    def is_empty(self) -> bool:
        return not self.raw_text


class BiopipeMDReader:
    """Read and parse BIOPIPE.md from project root."""

    FILENAME = "BIOPIPE.md"

    def read(self, directory: str | Path = ".") -> ProjectContext:
        """Search for BIOPIPE.md in directory and parents."""
        path = self._find_file(Path(directory))
        if path is None:
            return ProjectContext()

        text = path.read_text(encoding="utf-8", errors="replace")
        return self._parse(text)

    def _find_file(self, start: Path) -> Path | None:
        """Walk up directory tree looking for BIOPIPE.md."""
        current = start.resolve()
        for _ in range(10):  # max 10 levels up
            candidate = current / self.FILENAME
            if candidate.is_file():
                return candidate
            parent = current.parent
            if parent == current:
                break
            current = parent
        return None

    def _parse(self, text: str) -> ProjectContext:
        """Parse key-value pairs and conventions from BIOPIPE.md."""
        ctx = ProjectContext(raw_text=text)
        in_conventions = False

        for line in text.split("\n"):
            stripped = line.strip()
            if stripped.startswith("#") or not stripped:
                in_conventions = False
                continue

            if stripped.lower().startswith("conventions"):
                in_conventions = True
                continue

            if in_conventions and stripped.startswith("- "):
                ctx.conventions.append(stripped[2:].strip())
                continue

            if ":" in stripped and not in_conventions:
                key, _, value = stripped.partition(":")
                key = key.strip().lower()
                value = value.strip()
                if key == "organism":
                    ctx.organism = value
                elif key == "genome":
                    ctx.genome = value
                elif key in ("sequencing", "seq"):
                    ctx.sequencing = value
                elif key == "cluster":
                    ctx.cluster = value
                elif key == "partition":
                    ctx.partition = value
                elif key in ("adapters", "adapter"):
                    ctx.adapters = value
                else:
                    ctx.extra[key] = value

        return ctx
