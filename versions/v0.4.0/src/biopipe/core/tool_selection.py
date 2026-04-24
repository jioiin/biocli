"""Tool selection logic: deterministic rules for bioinformatics tools.

LLM can override, but defaults are rules, not hallucination.
RNA-seq → HISAT2/STAR (never BWA). WGS → BWA (never HISAT2).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ToolRecommendation:
    """Recommended tool with reasoning."""
    tool: str
    reason: str
    alternatives: list[str]
    warnings: list[str]


# Deterministic rules: pipeline_type → step → tool
_RULES: dict[str, dict[str, ToolRecommendation]] = {
    "rnaseq": {
        "qc": ToolRecommendation("fastqc", "Standard QC for all NGS", ["qualimap"], []),
        "trim": ToolRecommendation("fastp", "Faster than trimmomatic, auto-detects adapters", ["trimmomatic", "cutadapt"], []),
        "align": ToolRecommendation("hisat2", "Splice-aware aligner for RNA-seq", ["star"], ["NEVER use BWA for RNA-seq — BWA is not splice-aware"]),
        "quantify": ToolRecommendation("featurecounts", "Fast, accurate gene counting", ["htseq-count", "salmon", "kallisto"], []),
        "report": ToolRecommendation("multiqc", "Aggregates all QC reports", [], []),
    },
    "wgs": {
        "qc": ToolRecommendation("fastqc", "Standard QC", ["qualimap"], []),
        "trim": ToolRecommendation("fastp", "Fast trimming", ["trimmomatic"], []),
        "align": ToolRecommendation("bwa", "BWA-MEM for DNA alignment", ["minimap2", "bowtie2"], ["NEVER use HISAT2/STAR for WGS — those are RNA-seq aligners"]),
        "dedup": ToolRecommendation("gatk", "MarkDuplicates", ["picard", "sambamba"], ["Always mark duplicates for WGS/WES"]),
        "call": ToolRecommendation("gatk", "HaplotypeCaller for germline variants", ["freebayes", "deepvariant"], []),
        "report": ToolRecommendation("multiqc", "Aggregates all QC reports", [], []),
    },
    "wes": {
        "qc": ToolRecommendation("fastqc", "Standard QC", [], []),
        "trim": ToolRecommendation("fastp", "Fast trimming", ["trimmomatic"], []),
        "align": ToolRecommendation("bwa", "BWA-MEM for exome", ["minimap2"], []),
        "dedup": ToolRecommendation("gatk", "MarkDuplicates", ["picard"], []),
        "call": ToolRecommendation("gatk", "HaplotypeCaller", ["freebayes", "deepvariant"], ["Consider adding target BED file for WES"]),
        "report": ToolRecommendation("multiqc", "Aggregates reports", [], []),
    },
    "atacseq": {
        "qc": ToolRecommendation("fastqc", "Standard QC", [], []),
        "trim": ToolRecommendation("fastp", "Nextera adapter trimming", ["trimmomatic"], ["Use Nextera adapters, NOT TruSeq"]),
        "align": ToolRecommendation("bowtie2", "Standard for ATAC-seq", ["bwa"], ["Remove mitochondrial reads after alignment"]),
        "peaks": ToolRecommendation("macs2", "Peak calling for ATAC-seq", ["macs3"], ["Use --nomodel --shift -100 --extsize 200 for ATAC-seq"]),
        "report": ToolRecommendation("multiqc", "Aggregates reports", [], []),
    },
    "chipseq": {
        "qc": ToolRecommendation("fastqc", "Standard QC", [], []),
        "trim": ToolRecommendation("fastp", "Standard trimming", ["trimmomatic"], []),
        "align": ToolRecommendation("bowtie2", "Standard for ChIP-seq", ["bwa"], []),
        "dedup": ToolRecommendation("picard", "MarkDuplicates for ChIP", ["sambamba"], []),
        "peaks": ToolRecommendation("macs2", "Peak calling", ["homer"], ["Need input/control for proper peak calling"]),
        "report": ToolRecommendation("multiqc", "Aggregates reports", [], []),
    },
}


class ToolSelector:
    """Deterministic tool selection based on pipeline type."""

    def recommend(self, pipeline_type: str, step: str) -> ToolRecommendation | None:
        """Get recommended tool for a pipeline step."""
        rules = _RULES.get(pipeline_type.lower())
        if not rules:
            return None
        return rules.get(step.lower())

    def recommend_pipeline(self, pipeline_type: str) -> list[tuple[str, ToolRecommendation]]:
        """Get all recommended tools for a pipeline type."""
        rules = _RULES.get(pipeline_type.lower())
        if not rules:
            return []
        return list(rules.items())

    def validate_choice(self, pipeline_type: str, step: str, chosen_tool: str) -> list[str]:
        """Check if a tool choice is valid for a step. Return warnings."""
        rec = self.recommend(pipeline_type, step)
        if not rec:
            return []

        warnings: list[str] = []
        if chosen_tool.lower() != rec.tool.lower():
            if chosen_tool.lower() in [a.lower() for a in rec.alternatives]:
                warnings.append(f"{chosen_tool} is valid but {rec.tool} is recommended: {rec.reason}")
            else:
                warnings.extend(rec.warnings)
                warnings.append(f"Standard tool for {pipeline_type}/{step} is {rec.tool}, not {chosen_tool}")

        return warnings

    def available_pipelines(self) -> list[str]:
        """List all supported pipeline types."""
        return list(_RULES.keys())

    def format_for_llm(self, pipeline_type: str) -> str:
        """Format recommendations for LLM context."""
        steps = self.recommend_pipeline(pipeline_type)
        if not steps:
            return f"No rules for pipeline type: {pipeline_type}"

        parts = [f"<tool_rules pipeline='{pipeline_type}'>"]
        for step_name, rec in steps:
            parts.append(f"  {step_name}: {rec.tool} ({rec.reason})")
            if rec.warnings:
                for w in rec.warnings:
                    parts.append(f"    ⚠ {w}")
        parts.append("</tool_rules>")
        return "\n".join(parts)
