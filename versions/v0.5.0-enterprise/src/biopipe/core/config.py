"""BioPipe-CLI configuration.

Priority: CLI args > env vars > project biopipe.toml > global config > defaults.
"""

from __future__ import annotations

import os
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

    backend: str = "hf_local"  # Only local Hugging Face (GPT4All)
    ollama_url: str = "http://localhost:11434"
    model: str = "qwen2.5-coder-7b-instruct-q4_k_m.gguf"
    model_path: Path = field(
        default_factory=lambda: Path.home() / ".biopipe" / "models" / "qwen2.5-coder-7b-instruct-q4_k_m.gguf"
    )
    output_dir: Path = field(default_factory=lambda: Path("./biopipe_output"))
    max_iterations: int = 10
    permission_level: PermissionLevel = PermissionLevel.GENERATE
    safety_allowlist: tuple[str, ...] = ()  # tuple = immutable
    slurm_max_nodes: int = 4
    slurm_max_hours: int = 72
    log_file: Path | None = None
    log_level: str = "DEBUG"
    rag_top_k: int = 5
    rag_db_path: Path = field(
        default_factory=lambda: Path.home() / ".local/share/biopipe/chromadb"
    )
    llm_timeout: int = 60
    max_output_size: int = 10240

    @classmethod
    def load(cls) -> Config:
        """Merge all config sources. Returns frozen Config."""
        model = os.getenv("BIOPIPE_MODEL", "qwen2.5-coder-7b-instruct-q4_k_m.gguf")
        ollama_url = os.getenv("BIOPIPE_OLLAMA_URL", "http://localhost:11434")

        env_model_path = os.getenv("BIOPIPE_MODEL_PATH")
        if env_model_path:
            model_path = Path(env_model_path)
        else:
            model_path = Path.home() / ".biopipe" / "models" / model

        backend = os.getenv("BIOPIPE_BACKEND", "hf_local")

        # Preserve privacy hardening even when the default backend is local GGUF.
        if not any(h in ollama_url for h in ("localhost", "127.0.0.1", "::1")):
            raise ValueError(
                f"ollama_url must be localhost. Got: {ollama_url}. "
                "Remote URLs leak prompts to external servers."
            )

        cloud_patterns = ("-cloud", "cloud:", ":cloud")
        if any(pattern in model.lower() for pattern in cloud_patterns):
            raise ValueError(
                f"Cloud model '{model}' is blocked. "
                "Cloud models send prompts to external servers."
            )

        env_level = os.getenv("BIOPIPE_PERMISSION_LEVEL")
        level = PermissionLevel[env_level.upper()] if env_level else PermissionLevel.GENERATE
        env_output = os.getenv("BIOPIPE_OUTPUT_DIR")
        output_dir = Path(env_output) if env_output else Path("./biopipe_output")

        # Ensure allowlist doesn't contain dangerous tools
        _NEVER_ALLOW = frozenset({"rm", "sudo", "curl", "wget", "nc", "dd", "mkfs"})
        safe_allowlist = tuple(t for t in DEFAULT_ALLOWLIST if t not in _NEVER_ALLOW)

        return cls(
            backend=backend,
            ollama_url=ollama_url,
            model=model,
            model_path=model_path,
            output_dir=output_dir,
            permission_level=level,
            safety_allowlist=safe_allowlist,
        )
