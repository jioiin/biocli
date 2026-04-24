"""Task decomposition: break complex requests into substeps.

"Full WGS analysis" → 7 steps, each generated, validated, assembled.
Deterministic step ordering based on pipeline type.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SubTask:
    """Single substep of a complex task."""
    order: int
    name: str           # "quality_control", "trimming", "alignment", etc.
    description: str    # human-readable
    tool: str           # recommended tool
    depends_on: list[int] = field(default_factory=list)  # order numbers
    status: str = "pending"  # "pending", "generated", "validated", "failed"
    script_fragment: str = ""


@dataclass
class TaskPlan:
    """Decomposed task with ordered substeps."""
    original_request: str
    pipeline_type: str
    subtasks: list[SubTask]

    def format_for_user(self) -> str:
        """Show the plan to the user."""
        lines = [f"Task: {self.original_request}", f"Type: {self.pipeline_type}", ""]
        for st in self.subtasks:
            icon = {"pending": "○", "generated": "◐", "validated": "●", "failed": "✕"}
            lines.append(f"  {icon.get(st.status, '?')} Step {st.order}: {st.description} [{st.tool}]")
        return "\n".join(lines)

    def next_pending(self) -> SubTask | None:
        """Get next pending substep."""
        for st in self.subtasks:
            if st.status == "pending":
                return st
        return None

    def is_complete(self) -> bool:
        return all(st.status == "validated" for st in self.subtasks)

    def mark_generated(self, order: int, script: str) -> None:
        for st in self.subtasks:
            if st.order == order:
                st.status = "generated"
                st.script_fragment = script

    def mark_validated(self, order: int) -> None:
        for st in self.subtasks:
            if st.order == order:
                st.status = "validated"

    def mark_failed(self, order: int) -> None:
        for st in self.subtasks:
            if st.order == order:
                st.status = "failed"


# Predefined step templates per pipeline type
_TEMPLATES: dict[str, list[tuple[str, str, str]]] = {
    "rnaseq": [
        ("quality_control", "Raw read quality assessment", "fastqc"),
        ("trimming", "Adapter removal and quality filtering", "fastp"),
        ("alignment", "Splice-aware alignment to reference genome", "hisat2"),
        ("sorting_indexing", "Sort and index BAM file", "samtools"),
        ("quantification", "Gene-level read counting", "featurecounts"),
        ("report", "Aggregate QC reports", "multiqc"),
    ],
    "wgs": [
        ("quality_control", "Raw read quality assessment", "fastqc"),
        ("trimming", "Adapter removal and quality filtering", "fastp"),
        ("alignment", "Align reads to reference genome", "bwa"),
        ("sorting_indexing", "Sort and index BAM file", "samtools"),
        ("mark_duplicates", "Mark PCR duplicates", "gatk"),
        ("variant_calling", "Call germline variants", "gatk"),
        ("report", "Aggregate QC reports", "multiqc"),
    ],
    "wes": [
        ("quality_control", "Raw read quality assessment", "fastqc"),
        ("trimming", "Adapter removal and quality filtering", "fastp"),
        ("alignment", "Align reads to reference genome", "bwa"),
        ("sorting_indexing", "Sort and index BAM file", "samtools"),
        ("mark_duplicates", "Mark PCR duplicates", "gatk"),
        ("variant_calling", "Call variants in target regions", "gatk"),
        ("report", "Aggregate QC reports", "multiqc"),
    ],
    "atacseq": [
        ("quality_control", "Raw read quality assessment", "fastqc"),
        ("trimming", "Nextera adapter removal", "fastp"),
        ("alignment", "Align to reference genome", "bowtie2"),
        ("filter_mito", "Remove mitochondrial reads", "samtools"),
        ("peak_calling", "Call accessible chromatin peaks", "macs2"),
        ("report", "Aggregate QC reports", "multiqc"),
    ],
}


class TaskDecomposer:
    """Decompose complex bioinformatics requests into substeps."""

    def decompose(self, request: str, pipeline_type: str) -> TaskPlan:
        """Break a request into ordered substeps."""
        template = _TEMPLATES.get(pipeline_type.lower())
        if not template:
            # Fallback: single step
            return TaskPlan(
                original_request=request,
                pipeline_type=pipeline_type,
                subtasks=[SubTask(
                    order=1, name="custom", description=request,
                    tool="unknown",
                )],
            )

        subtasks: list[SubTask] = []
        for i, (name, desc, tool) in enumerate(template, 1):
            deps = [i - 1] if i > 1 else []
            subtasks.append(SubTask(
                order=i, name=name, description=desc,
                tool=tool, depends_on=deps,
            ))

        return TaskPlan(
            original_request=request,
            pipeline_type=pipeline_type,
            subtasks=subtasks,
        )

    def available_types(self) -> list[str]:
        return list(_TEMPLATES.keys())
