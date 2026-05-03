"""Reference Genome Manager: download, index, and validate genomes.

One-command genome setup:
    biopipe genome download hg38
    biopipe genome list
    biopipe genome status hg38
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class GenomePaths:
    """Paths to a reference genome and its indices."""
    fasta: Path
    fai: Path | None = None       # samtools faidx
    dict_file: Path | None = None  # picard/gatk dict
    bwa_index: Path | None = None  # bwa index prefix
    genome_name: str = ""
    indexed: bool = False

    def to_context(self) -> str:
        """Format for LLM context injection."""
        status = "✓ fully indexed" if self.indexed else "✗ missing indices"
        return (
            f"Genome: {self.genome_name} ({status})\n"
            f"  FASTA: {self.fasta}\n"
            f"  FAI: {self.fai or 'missing'}\n"
            f"  DICT: {self.dict_file or 'missing'}\n"
            f"  BWA: {self.bwa_index or 'missing'}"
        )


# ── Genome Registry ─────────────────────────────────────────────────────────

GENOME_REGISTRY: dict[str, dict[str, Any]] = {
    "hg38": {
        "url": "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/000/001/405/GCA_000001405.15_GRCh38/seqs_for_alignment_pipelines.ucsc_ids/GCA_000001405.15_GRCh38_no_alt_analysis_set.fna.gz",
        "description": "Human GRCh38/hg38 (no alt, analysis set)",
        "size_gb": 3.0,
        "sha256": None,
        "secure_supported": False,
    },
    "hg19": {
        "url": "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/000/001/405/GCA_000001405.14_GRCh37.p13/GCA_000001405.14_GRCh37.p13_assembly_structure/Primary_Assembly/assembled_chromosomes/FASTA/",
        "description": "Human GRCh37/hg19",
        "size_gb": 3.0,
        "sha256": None,
        "secure_supported": False,
    },
    "mm39": {
        "url": "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/000/001/635/GCA_000001635.9_GRCm39/GCA_000001635.9_GRCm39_genomic.fna.gz",
        "description": "Mouse GRCm39/mm39",
        "size_gb": 2.7,
        "sha256": None,
        "secure_supported": False,
    },
    "mm10": {
        "url": "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/000/001/635/GCA_000001635.8_GRCm38.p6/GCA_000001635.8_GRCm38.p6_genomic.fna.gz",
        "description": "Mouse GRCm38/mm10",
        "size_gb": 2.7,
        "sha256": None,
        "secure_supported": False,
    },
    "dm6": {
        "url": "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/000/001/215/GCA_000001215.4_Release_6_plus_ISO1_MT/GCA_000001215.4_Release_6_plus_ISO1_MT_genomic.fna.gz",
        "description": "Drosophila melanogaster dm6",
        "size_gb": 0.14,
        "sha256": None,
        "secure_supported": False,
    },
    "sacCer3": {
        "url": "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/000/146/045/GCF_000146045.2_R64/GCF_000146045.2_R64_genomic.fna.gz",
        "description": "Saccharomyces cerevisiae R64 (yeast)",
        "size_gb": 0.012,
        "sha256": None,
        "secure_supported": False,
    },
    "danRer11": {
        "url": "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/000/002/035/GCF_000002035.6_GRCz11/GCF_000002035.6_GRCz11_genomic.fna.gz",
        "description": "Zebrafish GRCz11/danRer11",
        "size_gb": 1.4,
        "sha256": None,
        "secure_supported": False,
    },
    "ce11": {
        "url": "https://ftp.ncbi.nlm.nih.gov/genomes/all/GCF/000/002/985/GCF_000002985.6_WBcel235/GCF_000002985.6_WBcel235_genomic.fna.gz",
        "description": "C. elegans WBcel235/ce11",
        "size_gb": 0.1,
        "sha256": None,
        "secure_supported": False,
    },
    "t2t-chm13": {
        "url": "https://s3-us-west-2.amazonaws.com/human-pangenomics/T2T/CHM13/assemblies/analysis_set/chm13v2.0.fa.gz",
        "description": "Human T2T-CHM13v2.0 (telomere-to-telomere)",
        "size_gb": 3.1,
        "sha256": None,
        "secure_supported": False,
    },
}


class GenomeManager:
    """Manage reference genomes: download, index, validate."""

    def __init__(self, base_dir: str | Path | None = None):
        if base_dir is None:
            base_dir = Path.home() / ".biopipe" / "genomes"
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)

    def list_available(self) -> list[dict[str, Any]]:
        """List all genomes in the registry with local status."""
        results = []
        for name, info in GENOME_REGISTRY.items():
            genome_dir = self._base / name
            fasta = genome_dir / f"{name}.fa"
            installed = fasta.exists()
            indexed = self._check_indices(name) if installed else False

            results.append({
                "name": name,
                "description": info["description"],
                "size_gb": info["size_gb"],
                "installed": installed,
                "indexed": indexed,
            })
        return results

    def status(self, genome: str) -> GenomePaths | None:
        """Get paths and index status for a genome."""
        genome_dir = self._base / genome
        fasta = genome_dir / f"{genome}.fa"

        if not fasta.exists():
            return None

        paths = GenomePaths(
            fasta=fasta,
            genome_name=genome,
        )

        # Check indices
        fai = fasta.with_suffix(".fa.fai")
        if fai.exists():
            paths.fai = fai

        dict_f = fasta.with_suffix(".dict")
        if dict_f.exists():
            paths.dict_file = dict_f

        bwa_prefix = fasta
        if (fasta.with_suffix(".fa.bwt")).exists() or (fasta.with_suffix(".fa.0123")).exists():
            paths.bwa_index = bwa_prefix

        paths.indexed = all([paths.fai, paths.dict_file, paths.bwa_index])
        return paths

    def download(
        self,
        genome: str,
        callback: Any = None,
        secure_profile: bool = False,
    ) -> GenomePaths:
        """Download a reference genome from NCBI/source.

        Args:
            genome: Genome name (e.g. "hg38")
            callback: Optional callback(message: str) for progress

        Returns:
            GenomePaths with the downloaded/indexed genome.
        """
        if genome not in GENOME_REGISTRY:
            available = ", ".join(sorted(GENOME_REGISTRY.keys()))
            raise ValueError(f"Unknown genome '{genome}'. Available: {available}")

        info = GENOME_REGISTRY[genome]
        genome_dir = self._base / genome
        genome_dir.mkdir(parents=True, exist_ok=True)

        fasta = genome_dir / f"{genome}.fa"
        fasta_gz = genome_dir / f"{genome}.fa.gz"

        # Download
        if not fasta.exists():
            if callback:
                callback(f"Downloading {genome} ({info['size_gb']} GB)...")

            try:
                subprocess.run(
                    ["wget", "-q", "-O", str(fasta_gz), info["url"]],
                    check=True, timeout=3600,
                )
            except FileNotFoundError:
                # wget not available, try curl
                subprocess.run(
                    ["curl", "-sL", "-o", str(fasta_gz), info["url"]],
                    check=True, timeout=3600,
                )

            self._verify_download_integrity(genome, info, fasta_gz, secure_profile)

            # Decompress
            if callback:
                callback(f"Decompressing {genome}...")
            subprocess.run(
                ["gunzip", "-f", str(fasta_gz)],
                check=True, timeout=600,
            )
        else:
            if callback:
                callback(f"{genome} FASTA already exists.")

        # Index
        self._index_genome(genome, fasta, callback)

        return self.status(genome)

    def _index_genome(self, genome: str, fasta: Path, callback: Any = None) -> None:
        """Create all indices for a genome."""
        # samtools faidx
        fai = fasta.with_suffix(".fa.fai")
        if not fai.exists() and shutil.which("samtools"):
            if callback:
                callback(f"Creating samtools index...")
            subprocess.run(
                ["samtools", "faidx", str(fasta)],
                check=True, timeout=600,
            )

        # sequence dictionary (for GATK)
        dict_f = fasta.with_suffix(".dict")
        if not dict_f.exists() and shutil.which("samtools"):
            if callback:
                callback(f"Creating sequence dictionary...")
            subprocess.run(
                ["samtools", "dict", str(fasta), "-o", str(dict_f)],
                check=True, timeout=600,
            )

        # BWA index
        bwt = fasta.with_suffix(".fa.bwt")
        bwt2 = fasta.with_suffix(".fa.0123")  # bwa-mem2
        if not bwt.exists() and not bwt2.exists():
            if shutil.which("bwa-mem2"):
                if callback:
                    callback(f"Creating BWA-MEM2 index (this takes a while)...")
                subprocess.run(
                    ["bwa-mem2", "index", str(fasta)],
                    check=True, timeout=7200,
                )
            elif shutil.which("bwa"):
                if callback:
                    callback(f"Creating BWA index (this takes a while)...")
                subprocess.run(
                    ["bwa", "index", str(fasta)],
                    check=True, timeout=7200,
                )

    def _check_indices(self, genome: str) -> bool:
        """Check if all indices exist."""
        paths = self.status(genome)
        return paths.indexed if paths else False

    def _verify_download_integrity(
        self,
        genome: str,
        info: dict[str, Any],
        fasta_gz: Path,
        secure_profile: bool,
    ) -> None:
        """Verify downloaded archive hash before decompressing."""
        if secure_profile and info.get("secure_supported") is False:
            raise ValueError(
                f"Secure profile unsupported for genome '{genome}': "
                "source is not marked as checksum-stable."
            )

        expected_sha256 = self._expected_sha256(info)
        if expected_sha256 is None:
            if secure_profile:
                raise ValueError(
                    f"Secure profile unsupported for genome '{genome}': "
                    "stable checksum is not configured."
                )
            return

        actual_sha256 = self._sha256_file(fasta_gz)
        if actual_sha256 != expected_sha256:
            fasta_gz.unlink(missing_ok=True)
            raise ValueError(
                f"SHA256 mismatch for genome '{genome}': "
                f"expected {expected_sha256}, got {actual_sha256}."
            )

    def _expected_sha256(self, info: dict[str, Any]) -> str | None:
        """Return expected archive SHA256 from registry metadata."""
        expected = info.get("sha256")
        if expected is None:
            return None
        return str(expected).strip().lower()

    def _sha256_file(self, path: Path) -> str:
        """Calculate SHA256 for a local file."""
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    def format_list(self) -> str:
        """Format genome list for display."""
        genomes = self.list_available()
        lines = [
            f"{'Name':<12} {'Description':<45} {'Size':<8} {'Status'}",
            "─" * 80,
        ]
        for g in genomes:
            if g["indexed"]:
                status = "✅ indexed"
            elif g["installed"]:
                status = "⚠️ needs indexing"
            else:
                status = "—"
            lines.append(
                f"{g['name']:<12} {g['description']:<45} {g['size_gb']:<8.1f} {status}"
            )
        return "\n".join(lines)
