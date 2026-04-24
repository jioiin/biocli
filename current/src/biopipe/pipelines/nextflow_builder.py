"""Nextflow Pipeline Builder: generate production-ready Nextflow DSL2 pipelines.

Converts a list of pipeline steps into a complete main.nf + nextflow.config
with proper channels, containers (Biocontainers), and profiles for
local/SLURM/cloud execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PipelineStep:
    """A single step in a bioinformatics pipeline."""
    name: str                    # e.g. "fastqc", "bwa_mem", "gatk_haplotypecaller"
    tool: str                    # e.g. "fastqc", "bwa", "gatk"
    command_template: str        # The actual command with placeholders
    inputs: list[str] = field(default_factory=list)    # Input channel names
    outputs: list[str] = field(default_factory=list)   # Output channel names
    container: str = ""          # Docker/Singularity image
    cpus: int = 1
    memory_gb: int = 4
    time_h: int = 1
    label: str = ""              # e.g. "process_medium"


# ── Default Step Templates ───────────────────────────────────────────────────

DEFAULT_STEPS: dict[str, PipelineStep] = {
    "fastqc": PipelineStep(
        name="fastqc", tool="fastqc",
        command_template='fastqc -t ${task.cpus} -o fastqc_out ${reads}',
        inputs=["reads"], outputs=["fastqc_results"],
        container="biocontainers/fastqc:0.12.1--hdfd78af_0",
        cpus=2, memory_gb=4, label="process_low",
    ),
    "fastp": PipelineStep(
        name="fastp", tool="fastp",
        command_template='fastp -i ${reads[0]} -I ${reads[1]} -o ${sample_id}_R1.trimmed.fq.gz -O ${sample_id}_R2.trimmed.fq.gz --thread ${task.cpus} -j ${sample_id}.fastp.json -h ${sample_id}.fastp.html',
        inputs=["reads"], outputs=["trimmed_reads", "fastp_report"],
        container="biocontainers/fastp:0.23.4--hadf994f_0",
        cpus=4, memory_gb=8, label="process_medium",
    ),
    "bwa_mem": PipelineStep(
        name="bwa_mem", tool="bwa",
        command_template='bwa mem -t ${task.cpus} -R "@RG\\\\tID:${sample_id}\\\\tSM:${sample_id}\\\\tPL:ILLUMINA" ${genome} ${reads[0]} ${reads[1]} | samtools sort -@ ${task.cpus} -o ${sample_id}.sorted.bam',
        inputs=["reads", "genome"], outputs=["sorted_bam"],
        container="biocontainers/bwa:0.7.18--he4a0461_0",
        cpus=8, memory_gb=16, time_h=4, label="process_high",
    ),
    "mark_duplicates": PipelineStep(
        name="mark_duplicates", tool="gatk",
        command_template='gatk MarkDuplicates -I ${bam} -O ${sample_id}.dedup.bam -M ${sample_id}.metrics.txt',
        inputs=["sorted_bam"], outputs=["dedup_bam"],
        container="broadinstitute/gatk:4.5.0.0",
        cpus=2, memory_gb=16, label="process_medium",
    ),
    "haplotypecaller": PipelineStep(
        name="haplotypecaller", tool="gatk",
        command_template='gatk HaplotypeCaller -R ${genome} -I ${bam} -O ${sample_id}.g.vcf.gz -ERC GVCF',
        inputs=["dedup_bam", "genome"], outputs=["gvcf"],
        container="broadinstitute/gatk:4.5.0.0",
        cpus=4, memory_gb=16, time_h=8, label="process_high",
    ),
    "samtools_index": PipelineStep(
        name="samtools_index", tool="samtools",
        command_template='samtools index ${bam}',
        inputs=["sorted_bam"], outputs=["bam_index"],
        container="biocontainers/samtools:1.19--h50ea8bc_0",
        cpus=1, memory_gb=4, label="process_low",
    ),
    "multiqc": PipelineStep(
        name="multiqc", tool="multiqc",
        command_template='multiqc . -o multiqc_report',
        inputs=["all_reports"], outputs=["multiqc_report"],
        container="biocontainers/multiqc:1.21--pyhdfd78af_0",
        cpus=1, memory_gb=4, label="process_low",
    ),
    "samtools_flagstat": PipelineStep(
        name="samtools_flagstat", tool="samtools",
        command_template='samtools flagstat ${bam} > ${sample_id}.flagstat.txt',
        inputs=["sorted_bam"], outputs=["flagstat"],
        container="biocontainers/samtools:1.19--h50ea8bc_0",
        cpus=1, memory_gb=2, label="process_low",
    ),
}


class NextflowBuilder:
    """Generate Nextflow DSL2 pipeline from step definitions."""

    def build(
        self,
        steps: list[PipelineStep],
        params: dict[str, Any] | None = None,
        genome: str = "hg38",
    ) -> dict[str, str]:
        """Generate main.nf and nextflow.config.

        Returns:
            Dict with keys "main.nf" and "nextflow.config".
        """
        if params is None:
            params = {}

        main_nf = self._build_main(steps, params, genome)
        config = self._build_config(steps, params)

        return {
            "main.nf": main_nf,
            "nextflow.config": config,
        }

    def build_from_names(self, step_names: list[str], **kwargs) -> dict[str, str]:
        """Build pipeline from step names using default templates."""
        steps = []
        for name in step_names:
            if name in DEFAULT_STEPS:
                steps.append(DEFAULT_STEPS[name])
            else:
                # Create a generic step
                steps.append(PipelineStep(
                    name=name, tool=name,
                    command_template=f"{name} ${{input}}",
                    inputs=["input"], outputs=["output"],
                ))
        return self.build(steps, **kwargs)

    def _build_main(
        self, steps: list[PipelineStep], params: dict, genome: str,
    ) -> str:
        """Generate main.nf content."""
        lines = [
            "#!/usr/bin/env nextflow",
            "",
            "/*",
            " * BioPipe-CLI Generated Pipeline",
            f" * Genome: {genome}",
            f" * Steps: {', '.join(s.name for s in steps)}",
            " * Generated by BioPipe-CLI (https://github.com/biopipe/biopipe-cli)",
            " */",
            "",
            "nextflow.enable.dsl = 2",
            "",
            "// ── Parameters ──────────────────────────────────────────",
            f'params.reads    = "{params.get("reads", "data/*_{{R1,R2}}.fastq.gz")}"',
            f'params.genome   = "{params.get("genome", "$HOME/.biopipe/genomes/" + genome + "/" + genome + ".fa")}"',
            f'params.outdir   = "{params.get("outdir", "results")}"',
            "",
        ]

        # Process definitions
        for step in steps:
            lines.extend(self._render_process(step))

        # Workflow
        lines.append("// ── Workflow ─────────────────────────────────────────────")
        lines.append("workflow {")
        lines.append("    // Create input channel")
        lines.append('    reads_ch = Channel.fromFilePairs(params.reads, checkIfExists: true)')
        lines.append('    genome_ch = Channel.value(file(params.genome))')
        lines.append("")

        # Chain processes
        prev_output = "reads_ch"
        for i, step in enumerate(steps):
            output_name = f"{step.name}_out"
            if "genome" in step.inputs and len(step.inputs) > 1:
                lines.append(f"    {output_name} = {step.name.upper()}({prev_output}, genome_ch)")
            else:
                lines.append(f"    {output_name} = {step.name.upper()}({prev_output})")
            prev_output = output_name

        lines.append("}")
        lines.append("")

        return "\n".join(lines)

    def _render_process(self, step: PipelineStep) -> list[str]:
        """Render a Nextflow process block."""
        lines = [
            f"// ── Process: {step.name} ──────────────────────────────────",
            f"process {step.name.upper()} {{",
        ]

        if step.label:
            lines.append(f"    label '{step.label}'")

        if step.container:
            lines.append(f"    container '{step.container}'")

        lines.append(f"    cpus {step.cpus}")
        lines.append(f"    memory '{step.memory_gb} GB'")
        lines.append(f"    time '{step.time_h}h'")
        lines.append("")
        lines.append("    publishDir \"${params.outdir}/" + step.name + "\", mode: 'copy'")
        lines.append("")

        # Input
        lines.append("    input:")
        lines.append("    tuple val(sample_id), path(reads)")
        if "genome" in step.inputs:
            lines.append("    path genome")
        lines.append("")

        # Output
        lines.append("    output:")
        lines.append(f"    tuple val(sample_id), path('*'), emit: results")
        lines.append("")

        # Script
        lines.append("    script:")
        lines.append('    """')
        lines.append(f"    {step.command_template}")
        lines.append('    """')
        lines.append("}")
        lines.append("")

        return lines

    def _build_config(self, steps: list[PipelineStep], params: dict) -> str:
        """Generate nextflow.config."""
        lines = [
            "/*",
            " * BioPipe-CLI Generated Configuration",
            " */",
            "",
            "// Pipeline metadata",
            "manifest {",
            "    name            = 'biopipe-pipeline'",
            "    author          = 'BioPipe-CLI'",
            "    description     = 'Auto-generated bioinformatics pipeline'",
            "    mainScript      = 'main.nf'",
            "    nextflowVersion = '>=23.04.0'",
            "    version         = '1.0.0'",
            "}",
            "",
            "// Execution profiles",
            "profiles {",
            "    standard {",
            "        process.executor = 'local'",
            "    }",
            "    slurm {",
            "        process.executor = 'slurm'",
            "        process.queue    = 'compute'",
            "        process.clusterOptions = '--account=default'",
            "    }",
            "    docker {",
            "        docker.enabled = true",
            "    }",
            "    singularity {",
            "        singularity.enabled = true",
            "        singularity.autoMounts = true",
            "    }",
            "}",
            "",
            "// Process labels",
            "process {",
            "    withLabel: 'process_low' {",
            "        cpus = 2",
            "        memory = '4 GB'",
            "        time = '1h'",
            "    }",
            "    withLabel: 'process_medium' {",
            "        cpus = 4",
            "        memory = '16 GB'",
            "        time = '4h'",
            "    }",
            "    withLabel: 'process_high' {",
            "        cpus = 8",
            "        memory = '32 GB'",
            "        time = '12h'",
            "    }",
            "}",
            "",
            "// Reports",
            "timeline.enabled = true",
            "report.enabled   = true",
            "trace.enabled    = true",
            "dag.enabled      = true",
            "",
        ]
        return "\n".join(lines)
