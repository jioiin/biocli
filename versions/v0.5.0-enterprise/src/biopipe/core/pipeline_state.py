"""Pipeline state: accumulated script and metadata that survives session compaction."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PipelineStep:
    """Single step in the pipeline."""
    order: int
    tool: str
    action: str
    flags: dict[str, str] = field(default_factory=dict)
    script_lines: str = ""


@dataclass
class PipelineState:
    """Accumulated pipeline — NEVER compacted, NEVER summarized.

    When SessionManager.compact() runs, messages get summarized.
    PipelineState persists intact. This is the source of truth.
    """
    steps: list[PipelineStep] = field(default_factory=list)
    reference_genome: str | None = None
    sequencing_type: str | None = None
    organism: str | None = None
    output_dir: str = "./biopipe_output"
    threads: int = 4
    current_script: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_step(self, step: PipelineStep) -> None:
        self.steps.append(step)
        self._rebuild_script()

    def update_script(self, new_script: str) -> None:
        self.current_script = new_script

    def format_for_llm(self) -> str:
        """Format for LLM context. Replaces conversation history as source of truth."""
        parts = [
            "<pipeline_state>",
            f"Reference genome: {self.reference_genome or 'not set'}",
            f"Sequencing: {self.sequencing_type or 'not set'}",
            f"Organism: {self.organism or 'not set'}",
            f"Steps: {len(self.steps)}",
        ]
        if self.steps:
            for s in self.steps:
                parts.append(f"  {s.order}. {s.tool} — {s.action}")
        parts.append(f"\nCurrent script:\n{self.current_script or '(empty)'}")
        parts.append("</pipeline_state>")
        return "\n".join(parts)

    def is_empty(self) -> bool:
        return len(self.steps) == 0

    def _rebuild_script(self) -> None:
        lines = []
        for step in self.steps:
            if step.script_lines:
                lines.append(f"\n# ---- Step {step.order}: {step.action} ----")
                lines.append(step.script_lines)
        self.current_script = "\n".join(lines)
