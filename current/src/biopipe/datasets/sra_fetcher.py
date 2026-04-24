"""SRA/GEO Dataset Fetcher: download sequencing data from NCBI.

Supports SRR, SRX, SRP, GSE, GSM accession IDs.
Uses fasterq-dump (SRA Toolkit) for parallel FASTQ download.
"""

from __future__ import annotations

import os
import re
import subprocess
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class FetchResult:
    """Result of an SRA fetch operation."""
    accession: str
    files: list[Path]
    paired: bool = False
    size_mb: float = 0.0
    error: str = ""


ACCESSION_PATTERNS = {
    "srr": re.compile(r"^[SDE]RR\d+$", re.IGNORECASE),       # Run
    "srx": re.compile(r"^[SDE]RX\d+$", re.IGNORECASE),       # Experiment
    "srp": re.compile(r"^[SDE]RP\d+$", re.IGNORECASE),       # Project
    "gse": re.compile(r"^GSE\d+$", re.IGNORECASE),            # GEO Series
    "gsm": re.compile(r"^GSM\d+$", re.IGNORECASE),            # GEO Sample
}


def classify_accession(accession: str) -> str:
    """Classify an NCBI accession type."""
    for acc_type, pattern in ACCESSION_PATTERNS.items():
        if pattern.match(accession):
            return acc_type
    return "unknown"


class SRAFetcher:
    """Download FASTQ data from NCBI SRA."""

    def __init__(self, output_dir: str | Path | None = None):
        self._output = Path(output_dir) if output_dir else Path.cwd()
        self._output.mkdir(parents=True, exist_ok=True)

    def fetch(
        self,
        accession: str,
        threads: int = 4,
        paired: bool = True,
        callback: Any = None,
    ) -> FetchResult:
        """Download FASTQ files for an accession.

        Args:
            accession: NCBI accession (SRR/SRX/SRP/GSE/GSM)
            threads: Number of download threads
            paired: Whether to split paired-end reads
            callback: Optional progress callback(message: str)

        Returns:
            FetchResult with downloaded file paths.
        """
        acc_type = classify_accession(accession)

        if acc_type == "unknown":
            return FetchResult(
                accession=accession,
                files=[],
                error=f"Unknown accession format: {accession}. Expected SRR/SRX/SRP/GSE/GSM.",
            )

        # Check for SRA Toolkit
        if not shutil.which("fasterq-dump") and not shutil.which("fastq-dump"):
            return FetchResult(
                accession=accession,
                files=[],
                error=(
                    "SRA Toolkit not found. Install:\n"
                    "  conda install -c bioconda sra-tools\n"
                    "  OR: https://github.com/ncbi/sra-tools/wiki/01.-Downloading-SRA-Toolkit"
                ),
            )

        # For project-level accessions, resolve run accessions first
        if acc_type in ("srp", "srx", "gse", "gsm"):
            run_accessions = self._resolve_runs(accession, callback)
            if not run_accessions:
                return FetchResult(
                    accession=accession,
                    files=[],
                    error=f"Could not resolve runs for {accession}. Check NCBI connectivity.",
                )
            # Fetch each run
            all_files = []
            for run_acc in run_accessions:
                if callback:
                    callback(f"Fetching {run_acc}...")
                result = self._fetch_run(run_acc, threads, paired, callback)
                all_files.extend(result.files)
            return FetchResult(
                accession=accession,
                files=all_files,
                paired=paired,
            )
        else:
            return self._fetch_run(accession, threads, paired, callback)

    def _fetch_run(
        self, accession: str, threads: int, paired: bool, callback: Any,
    ) -> FetchResult:
        """Download a single SRR run."""
        out_dir = self._output / accession
        out_dir.mkdir(parents=True, exist_ok=True)

        if callback:
            callback(f"Downloading {accession} with fasterq-dump...")

        try:
            # Prefer fasterq-dump (faster, multi-threaded)
            if shutil.which("fasterq-dump"):
                cmd = [
                    "fasterq-dump",
                    accession,
                    "--outdir", str(out_dir),
                    "--threads", str(threads),
                    "--progress",
                ]
                if paired:
                    cmd.append("--split-3")

                subprocess.run(cmd, check=True, timeout=3600)
            else:
                # Fallback to fastq-dump
                cmd = [
                    "fastq-dump",
                    accession,
                    "--outdir", str(out_dir),
                    "--gzip",
                ]
                if paired:
                    cmd.append("--split-3")

                subprocess.run(cmd, check=True, timeout=3600)

        except subprocess.CalledProcessError as e:
            return FetchResult(
                accession=accession,
                files=[],
                error=f"Download failed: {e}",
            )
        except subprocess.TimeoutExpired:
            return FetchResult(
                accession=accession,
                files=[],
                error="Download timed out (>1 hour)",
            )

        # Collect output files
        files = sorted(out_dir.glob(f"{accession}*"))
        total_size = sum(f.stat().st_size for f in files) / (1024 * 1024)

        if callback:
            callback(f"Downloaded {len(files)} files ({total_size:.1f} MB)")

        return FetchResult(
            accession=accession,
            files=files,
            paired=len(files) >= 2,
            size_mb=total_size,
        )

    def _resolve_runs(self, accession: str, callback: Any) -> list[str]:
        """Resolve project/experiment to run accessions using esearch/efetch."""
        if callback:
            callback(f"Resolving {accession} to run accessions...")

        # Try using NCBI Entrez Direct (if installed)
        if shutil.which("esearch"):
            try:
                result = subprocess.run(
                    ["bash", "-c",
                     f"esearch -db sra -query {accession} | efetch -format runinfo | cut -d',' -f1 | grep '^[SDE]RR'"],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip().splitlines()
            except Exception:
                pass

        # Fallback: try prefetch which can handle SRP accessions
        if shutil.which("prefetch"):
            try:
                result = subprocess.run(
                    ["prefetch", "--list", accession],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode == 0:
                    runs = [
                        line.strip() for line in result.stdout.splitlines()
                        if re.match(r"^[SDE]RR\d+", line.strip())
                    ]
                    if runs:
                        return runs
            except Exception:
                pass

        return []
