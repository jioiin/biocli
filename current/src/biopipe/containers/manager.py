"""Biocontainer Manager: resolve bioinformatics tools to container images.

Maps tool names to Docker/Singularity URIs from BioContainers and
Broad Institute registries. Supports both Docker and Singularity pull.
"""

from __future__ import annotations

import subprocess
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ContainerImage:
    """A container image for a bioinformatics tool."""
    tool: str
    docker_uri: str
    singularity_uri: str = ""
    version: str = ""
    size_mb: float = 0.0


# ── Container Registry ──────────────────────────────────────────────────────

CONTAINER_REGISTRY: dict[str, ContainerImage] = {
    # QC
    "fastqc": ContainerImage("fastqc", "biocontainers/fastqc:0.12.1--hdfd78af_0", version="0.12.1"),
    "multiqc": ContainerImage("multiqc", "biocontainers/multiqc:1.21--pyhdfd78af_0", version="1.21"),
    "fastp": ContainerImage("fastp", "biocontainers/fastp:0.23.4--hadf994f_0", version="0.23.4"),
    "trimmomatic": ContainerImage("trimmomatic", "biocontainers/trimmomatic:0.39--hdfd78af_2", version="0.39"),
    "trim_galore": ContainerImage("trim_galore", "biocontainers/trim-galore:0.6.10--hdfd78af_0", version="0.6.10"),
    "cutadapt": ContainerImage("cutadapt", "biocontainers/cutadapt:4.6--py39hf95cd2a_1", version="4.6"),

    # Alignment
    "bwa": ContainerImage("bwa", "biocontainers/bwa:0.7.18--he4a0461_0", version="0.7.18"),
    "bwa-mem2": ContainerImage("bwa-mem2", "biocontainers/bwa-mem2:2.2.1--he513fc3_0", version="2.2.1"),
    "hisat2": ContainerImage("hisat2", "biocontainers/hisat2:2.2.1--h87f3376_4", version="2.2.1"),
    "bowtie2": ContainerImage("bowtie2", "biocontainers/bowtie2:2.5.3--py39h6fed5c7_0", version="2.5.3"),
    "star": ContainerImage("star", "biocontainers/star:2.7.11b--h43eeafb_0", version="2.7.11b"),
    "minimap2": ContainerImage("minimap2", "biocontainers/minimap2:2.28--he4a0461_0", version="2.28"),

    # SAM/BAM
    "samtools": ContainerImage("samtools", "biocontainers/samtools:1.19--h50ea8bc_0", version="1.19"),
    "sambamba": ContainerImage("sambamba", "biocontainers/sambamba:1.0.1--h6f6fda4_0", version="1.0.1"),
    "picard": ContainerImage("picard", "broadinstitute/picard:3.1.1", version="3.1.1"),

    # Variant Calling
    "gatk": ContainerImage("gatk", "broadinstitute/gatk:4.5.0.0", version="4.5.0.0"),
    "bcftools": ContainerImage("bcftools", "biocontainers/bcftools:1.19--h8b25389_0", version="1.19"),
    "freebayes": ContainerImage("freebayes", "biocontainers/freebayes:1.3.7--h1870644_0", version="1.3.7"),
    "deepvariant": ContainerImage("deepvariant", "google/deepvariant:1.6.1", version="1.6.1"),

    # Annotation
    "snpeff": ContainerImage("snpeff", "biocontainers/snpsift:5.2--hdfd78af_0", version="5.2"),
    "vep": ContainerImage("vep", "ensemblorg/ensembl-vep:112.0", version="112.0"),

    # RNA-seq quantification
    "salmon": ContainerImage("salmon", "biocontainers/salmon:1.10.3--h6dccd9a_0", version="1.10.3"),
    "kallisto": ContainerImage("kallisto", "biocontainers/kallisto:0.50.1--h6de1650_0", version="0.50.1"),
    "rsem": ContainerImage("rsem", "biocontainers/rsem:1.3.3--pl5321h6b7c446_7", version="1.3.3"),
    "subread": ContainerImage("subread", "biocontainers/subread:2.0.6--he4a0461_0", version="2.0.6"),

    # Utilities
    "bedtools": ContainerImage("bedtools", "biocontainers/bedtools:2.31.1--hf5e1c6e_0", version="2.31.1"),
    "seqkit": ContainerImage("seqkit", "biocontainers/seqkit:2.7.0--h9ee0642_0", version="2.7.0"),

    # Pipeline
    "nextflow": ContainerImage("nextflow", "nextflow/nextflow:24.04.2", version="24.04.2"),
}


class BiocontainerManager:
    """Resolve bioinformatics tools to container images."""

    def __init__(self, cache_dir: str | Path | None = None):
        if cache_dir is None:
            cache_dir = Path.home() / ".biopipe" / "containers"
        self._cache = Path(cache_dir)
        self._cache.mkdir(parents=True, exist_ok=True)

    def resolve(self, tool_name: str) -> ContainerImage | None:
        """Resolve a tool name to its container image."""
        return CONTAINER_REGISTRY.get(tool_name.lower())

    def resolve_many(self, tools: list[str]) -> dict[str, ContainerImage]:
        """Resolve multiple tools at once."""
        results = {}
        for tool in tools:
            img = self.resolve(tool)
            if img:
                results[tool] = img
        return results

    def list_all(self) -> list[ContainerImage]:
        """List all available containers."""
        return list(CONTAINER_REGISTRY.values())

    def pull_singularity(self, tool_name: str, callback: Any = None) -> Path | None:
        """Pull a Singularity image for a tool.

        Returns path to the .sif file.
        """
        img = self.resolve(tool_name)
        if not img:
            return None

        sif_path = self._cache / f"{tool_name}_{img.version}.sif"
        if sif_path.exists():
            if callback:
                callback(f"Using cached {sif_path.name}")
            return sif_path

        # Determine pull command
        puller = "singularity" if shutil.which("singularity") else "apptainer"
        if not shutil.which(puller):
            if callback:
                callback("Neither Singularity nor Apptainer found.")
            return None

        if callback:
            callback(f"Pulling {img.docker_uri}...")

        try:
            subprocess.run(
                [puller, "pull", str(sif_path), f"docker://{img.docker_uri}"],
                check=True, timeout=1800,
            )
            return sif_path
        except Exception as e:
            if callback:
                callback(f"Pull failed: {e}")
            return None

    def format_list(self) -> str:
        """Format container list for display."""
        lines = [
            f"{'Tool':<18} {'Version':<10} {'Image'}",
            "─" * 80,
        ]
        for img in sorted(CONTAINER_REGISTRY.values(), key=lambda x: x.tool):
            lines.append(f"{img.tool:<18} {img.version:<10} {img.docker_uri}")
        return "\n".join(lines)
