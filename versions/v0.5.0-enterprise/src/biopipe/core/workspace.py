"""Workspace scanner: discovers files in the project directory.

Identifies FASTQ, BAM, VCF, GTF, reference genomes, existing scripts.
All operations are local os.listdir/os.stat — no network.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FileInfo:
    """Metadata about a discovered file."""
    path: str
    name: str
    size_bytes: int
    size_human: str
    extension: str
    category: str  # "fastq", "bam", "vcf", "reference", "script", "config", "other"


@dataclass
class WorkspaceSummary:
    """Summary of the current workspace."""
    root: str
    files: list[FileInfo] = field(default_factory=list)
    total_size_bytes: int = 0
    file_counts: dict[str, int] = field(default_factory=dict)
    paired_groups: dict[str, list[str]] = field(default_factory=dict)
    samplesheet_headers: list[str] = field(default_factory=list)

    def format_for_llm(self) -> str:
        """Format workspace summary for LLM context."""
        parts = ["<workspace>", f"Directory: {self.root}"]
        for cat, count in sorted(self.file_counts.items()):
            parts.append(f"  {cat}: {count} files")
            
        if self.paired_groups:
            parts.append("\nDetected Paired-End Samples:")
            for sample, pair in list(self.paired_groups.items())[:20]: # show up to 20 samples
                parts.append(f"  {sample}: {pair}")
        
        if self.samplesheet_headers:
            parts.append(f"\nDiscovered Metadata Columns (from samplesheet): {', '.join(self.samplesheet_headers)}")

        if self.files:
            parts.append("\nFiles:")
            for f in self.files[:50]:  # cap at 50 to save tokens
                parts.append(f"  [{f.category}] {f.name} ({f.size_human})")
        parts.append("</workspace>")
        return "\n".join(parts)

    def has_files(self, category: str) -> bool:
        return self.file_counts.get(category, 0) > 0


_CATEGORY_MAP: dict[str, str] = {
    ".fastq": "fastq", ".fq": "fastq",
    ".fastq.gz": "fastq", ".fq.gz": "fastq",
    ".bam": "bam", ".sam": "bam", ".cram": "bam",
    ".vcf": "vcf", ".vcf.gz": "vcf", ".bcf": "vcf",
    ".gtf": "annotation", ".gff": "annotation", ".gff3": "annotation",
    ".bed": "regions", ".bedpe": "regions",
    ".fa": "reference", ".fasta": "reference", ".fa.gz": "reference",
    ".fai": "reference", ".dict": "reference",
    ".sh": "script", ".bash": "script",
    ".py": "script", ".nf": "pipeline", ".smk": "pipeline", "Snakefile": "pipeline",
    ".toml": "config", ".yaml": "config", ".yml": "config", ".json": "config",
    ".csv": "metadata", ".tsv": "metadata", ".txt": "metadata",
    ".html": "report", ".zip": "report",
    ".log": "log",
}


class WorkspaceScanner:
    """Scan the current working directory for bioinformatics files."""

    def __init__(self, max_depth: int = 3) -> None:
        self._max_depth = max_depth

    def scan(self, root: str | Path = ".") -> WorkspaceSummary:
        """Scan directory tree and categorize files."""
        root_path = Path(root).resolve()
        summary = WorkspaceSummary(root=str(root_path))
        counts: dict[str, int] = {}

        for file_path in self._walk(root_path, depth=0):
            info = self._classify(file_path, root_path)
            summary.files.append(info)
            summary.total_size_bytes += info.size_bytes
            counts[info.category] = counts.get(info.category, 0) + 1

        summary.file_counts = counts
        summary.files.sort(key=lambda f: (f.category, f.name))
        
        self._detect_biological_heuristics(summary, root_path)
        
        return summary
        
    def _detect_biological_heuristics(self, summary: WorkspaceSummary, root_path: Path) -> None:
        import re
        import csv
        
        # Detect paired-end fastq reads
        fastq_files = [f.name for f in summary.files if f.category == "fastq"]
        pairs = {}
        for f in fastq_files:
            # Common patterns: sample_R1.fastq.gz, sample_1.fq
            match = re.search(r"^(.*?)(_R?[12])(\.fastq|\.fq)", f, re.IGNORECASE)
            if match:
                sample_name = match.group(1)
                read_num = match.group(2) # _R1 or _R2
                if sample_name not in pairs:
                    pairs[sample_name] = []
                pairs[sample_name].append(f)
        
        for sample, files in pairs.items():
            if len(files) == 2:
                summary.paired_groups[sample] = sorted(files)
                
        # Parse Samplesheet headers if present
        for f in summary.files:
            if f.category == "metadata" and "sample" in f.name.lower():
                try:
                    with open(root_path / f.path, "r", encoding="utf-8") as csvfile:
                        sniffer = csv.Sniffer()
                        sample = csvfile.read(1024)
                        csvfile.seek(0)
                        dialect = sniffer.sniff(sample)
                        reader = csv.reader(csvfile, dialect)
                        summary.samplesheet_headers = next(reader)
                        break
                except Exception:
                    pass

    def _walk(self, path: Path, depth: int) -> list[Path]:
        """Walk directory tree up to max_depth."""
        if depth > self._max_depth:
            return []
        results: list[Path] = []
        try:
            for entry in sorted(path.iterdir()):
                if entry.name.startswith("."):
                    continue
                if entry.is_file():
                    results.append(entry)
                elif entry.is_dir() and entry.name not in {
                    "__pycache__", "node_modules", ".git", ".snakemake"
                }:
                    results.extend(self._walk(entry, depth + 1))
        except PermissionError:
            import logging
            logging.warning(f"Permission denied while scanning: {path}")
        return results

    def _classify(self, path: Path, root: Path) -> FileInfo:
        """Classify a file by extension."""
        name = path.name
        size = path.stat().st_size

        # Handle double extensions like .fastq.gz
        category = "other"
        for ext, cat in _CATEGORY_MAP.items():
            if name.endswith(ext):
                category = cat
                break

        return FileInfo(
            path=str(path.relative_to(root)),
            name=name,
            size_bytes=size,
            size_human=self._human_size(size),
            extension=path.suffix,
            category=category,
        )

    @staticmethod
    def _human_size(size: int) -> str:
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024:
                return f"{size:.1f} {unit}" if unit != "B" else f"{size} B"
            size //= 1024
        return f"{size} PB"
