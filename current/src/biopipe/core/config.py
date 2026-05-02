"""BioPipe-CLI configuration.

Priority: CLI args > env vars > project biopipe.toml > global config > defaults.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse
from dataclasses import dataclass, field
from pathlib import Path

from .types import PermissionLevel

DEFAULT_ALLOWLIST: list[str] = [
    "fastqc", "multiqc", "qualimap", "preseq", "rseqc",
    "fastp", "trimmomatic", "cutadapt", "bbduk",
    "bwa", "bowtie2", "hisat2", "star", "minimap2", "salmon", "kallisto",
    "samtools", "sambamba", "picard",
    "gatk", "bcftools", "freebayes", "deepvariant", "strelka2",
    "snpeff", "annovar", "vep",
    "featurecounts", "htseq-count", "stringtie", "cufflinks",
    "macs2", "macs3", "homer",
    "bedtools", "seqtk", "bbtools", "tabix", "bgzip",
    "md5sum", "sha256sum", "wc", "sort", "awk", "grep", "sed", "cut",
    "head", "tail", "cat", "zcat", "gzip", "gunzip", "pigz",
    "ln", "cp", "mv", "tee", "xargs",
    "singularity", "apptainer", "conda", "mamba",
    "nextflow", "snakemake",
]


@dataclass(frozen=True)
class Config:
    """Frozen after creation. Cannot be modified at runtime."""

    ollama_url: str = "http://localhost:11434"
    model: str = "llama3:8b-instruct-q4_K_M"
    output_dir: Path = field(default_factory=lambda: Path("./biopipe_output"))
    max_iterations: int = 10
    permission_level: PermissionLevel = PermissionLevel.GENERATE
    safety_allowlist: tuple[str, ...] = ()  # tuple = immutable
    slurm_max_nodes: int = 4
    slurm_max_hours: int = 72
    log_file: Path | None = None
    log_level: str = "INFO"
    rag_top_k: int = 5
    rag_db_path: Path = field(
        default_factory=lambda: Path.home() / ".local/share/biopipe/chromadb"
    )
    llm_timeout: int = 60
    max_output_size: int = 10240

    @classmethod
    def load(cls) -> Config:
        """Merge all config sources. Returns frozen Config."""
        ollama_url = os.getenv("BIOPIPE_OLLAMA_URL", "http://localhost:11434")
        model = os.getenv("BIOPIPE_MODEL", "llama3:8b-instruct-q4_K_M")
        env_level = os.getenv("BIOPIPE_PERMISSION_LEVEL")
        level = PermissionLevel[env_level.upper()] if env_level else PermissionLevel.GENERATE
        env_output = os.getenv("BIOPIPE_OUTPUT_DIR")
        output_dir = Path(env_output) if env_output else Path("./biopipe_output")

        # Validate ollama_url: parsed hostname must be local-only
        parsed_url = urlparse(ollama_url)
        hostname = parsed_url.hostname
        if hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError(
                f"ollama_url must be localhost. Got: {ollama_url}. "
                f"Remote URLs leak prompts to external servers."
            )

        # Block cloud models — they send prompts to Ollama's servers
        _CLOUD_PATTERNS = ("-cloud", "cloud:", ":cloud")
        if any(p in model.lower() for p in _CLOUD_PATTERNS):
            raise ValueError(
                f"Cloud model '{model}' is blocked. "
                f"Cloud models send prompts to external servers. "
                f"Use a local model: qwen2.5-coder:14b, llama3.3:8b, etc."
            )

        # Ensure allowlist doesn't contain dangerous tools
        _NEVER_ALLOW = frozenset({"rm", "sudo", "curl", "wget", "nc", "dd", "mkfs"})
        safe_allowlist = tuple(t for t in DEFAULT_ALLOWLIST if t not in _NEVER_ALLOW)

        return cls(
            ollama_url=ollama_url,
            model=model,
            output_dir=output_dir,
            permission_level=level,
            safety_allowlist=safe_allowlist,
        )
