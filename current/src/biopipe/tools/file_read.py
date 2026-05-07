"""Built-in tool: Managed file reader for bioinformatics formats.

Reads files with auto-detection of bioinformatics formats (FASTQ, BAM header,
VCF header, Snakefile, Nextflow, config). Enforces size limits and blocks
binary data for safety.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from biopipe.core.types import Tool
from biopipe.core.privacy import PrivacyScrubber



# ── Format Detection ─────────────────────────────────────────────────────────

BIO_EXTENSIONS = {
    ".fastq": "fastq", ".fq": "fastq", ".fastq.gz": "fastq_gz",
    ".fq.gz": "fastq_gz",
    ".sam": "sam", ".bam": "bam", ".cram": "cram",
    ".vcf": "vcf", ".vcf.gz": "vcf_gz", ".bcf": "bcf",
    ".bed": "bed", ".gff": "gff", ".gtf": "gtf", ".gff3": "gff",
    ".fa": "fasta", ".fasta": "fasta", ".fna": "fasta",
    ".nf": "nextflow", ".config": "config",
    ".smk": "snakemake", ".yaml": "yaml", ".yml": "yaml",
    ".json": "json", ".toml": "toml",
    ".sh": "bash", ".py": "python", ".r": "r", ".R": "r",
    ".tsv": "tsv", ".csv": "csv",
    ".log": "log", ".out": "log", ".err": "log",
}

BINARY_FORMATS = {"bam", "cram", "bcf", "fastq_gz", "vcf_gz"}

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_LINES_PREVIEW = 200
HEADER_LINES = 50
ACCESS_DENIED_ERROR = "Access denied outside workspace"

_SYSTEM_BLOCKED_PREFIXES = (
    Path("/etc"),
    Path("/proc"),
    Path("/sys"),
    Path("/dev"),
)


def detect_format(path: Path) -> str:
    """Detect bioinformatics file format from extension."""
    name = path.name.lower()
    # Check double extensions first (.fastq.gz, .vcf.gz)
    for ext in sorted(BIO_EXTENSIONS.keys(), key=len, reverse=True):
        if name.endswith(ext):
            return BIO_EXTENSIONS[ext]
    suffix = path.suffix.lower()
    return BIO_EXTENSIONS.get(suffix, "text")


def read_bio_file(path: Path, max_lines: int = MAX_LINES_PREVIEW) -> dict[str, Any]:
    """Read a file with bioinformatics-aware handling.

    Returns dict with: content, format, lines_read, total_lines, truncated, metadata.
    """
    if not path.exists():
        return {"error": f"File not found: {path}", "content": ""}

    file_size = path.stat().st_size
    if file_size > MAX_FILE_SIZE:
        return {
            "error": f"File too large: {file_size / 1024 / 1024:.1f} MB (max {MAX_FILE_SIZE / 1024 / 1024:.0f} MB)",
            "content": "",
            "format": detect_format(path),
            "size_bytes": file_size,
        }

    fmt = detect_format(path)

    # Binary formats — extract header only
    if fmt in BINARY_FORMATS:
        return _read_binary_header(path, fmt)

    # Text formats
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"error": str(e), "content": ""}

    lines = content.splitlines()
    total_lines = len(lines)
    truncated = total_lines > max_lines

    if truncated:
        preview = "\n".join(lines[:max_lines])
    else:
        preview = content

    metadata = _extract_metadata(lines, fmt)

    return {
        "content": preview,
        "format": fmt,
        "lines_read": min(total_lines, max_lines),
        "total_lines": total_lines,
        "truncated": truncated,
        "size_bytes": file_size,
        "metadata": metadata,
    }


def _read_binary_header(path: Path, fmt: str) -> dict[str, Any]:
    """Extract header info from binary formats using CLI tools."""
    import subprocess

    header = ""

    if fmt in ("bam", "cram"):
        try:
            result = subprocess.run(
                ["samtools", "view", "-H", str(path)],
                capture_output=True, text=True, timeout=10,
            )
            header = result.stdout[:5000] if result.returncode == 0 else f"samtools error: {result.stderr}"
        except FileNotFoundError:
            header = "(samtools not found — install to read BAM/CRAM headers)"
        except subprocess.TimeoutExpired:
            header = "(timeout reading header)"

    elif fmt in ("bcf", "vcf_gz"):
        try:
            result = subprocess.run(
                ["bcftools", "view", "-h", str(path)],
                capture_output=True, text=True, timeout=10,
            )
            header = result.stdout[:5000] if result.returncode == 0 else f"bcftools error: {result.stderr}"
        except FileNotFoundError:
            header = "(bcftools not found — install to read BCF/VCF.GZ headers)"
        except subprocess.TimeoutExpired:
            header = "(timeout reading header)"

    elif fmt == "fastq_gz":
        import gzip
        try:
            with gzip.open(path, "rt") as f:
                lines = []
                for i, line in enumerate(f):
                    if i >= HEADER_LINES * 4:  # 4 lines per FASTQ record
                        break
                    lines.append(line.rstrip())
                header = "\n".join(lines)
        except Exception as e:
            header = f"(error reading gzip: {e})"

    return {
        "content": header,
        "format": fmt,
        "binary": True,
        "size_bytes": path.stat().st_size,
        "metadata": {"note": "Binary file — showing header only"},
    }


def _extract_metadata(lines: list[str], fmt: str) -> dict[str, Any]:
    """Extract quick metadata from file content."""
    meta: dict[str, Any] = {}

    if fmt == "fastq" and len(lines) >= 4:
        # Count records (every 4 lines = 1 read)
        meta["estimated_reads"] = len(lines) // 4
        # Read length from first record
        if len(lines) >= 2:
            meta["read_length"] = len(lines[1].strip())
        # Check if paired (common naming)
        if lines[0].startswith("@") and ("/1" in lines[0] or "/2" in lines[0]):
            meta["paired"] = True

    elif fmt == "vcf":
        header_lines = [l for l in lines if l.startswith("#")]
        data_lines = [l for l in lines if not l.startswith("#") and l.strip()]
        meta["header_lines"] = len(header_lines)
        meta["variant_count"] = len(data_lines)
        # Extract samples from #CHROM line
        chrom_line = [l for l in header_lines if l.startswith("#CHROM")]
        if chrom_line:
            fields = chrom_line[0].split("\t")
            if len(fields) > 9:
                meta["samples"] = fields[9:]
                meta["sample_count"] = len(fields) - 9

    elif fmt == "sam":
        header_lines = [l for l in lines if l.startswith("@")]
        meta["header_lines"] = len(header_lines)
        meta["alignment_count"] = len(lines) - len(header_lines)

    elif fmt in ("bed", "gff", "gtf"):
        data_lines = [l for l in lines if not l.startswith("#") and l.strip()]
        meta["feature_count"] = len(data_lines)

    elif fmt == "nextflow":
        processes = [l for l in lines if l.strip().startswith("process ")]
        meta["process_count"] = len(processes)

    elif fmt == "snakemake":
        rules = [l for l in lines if l.strip().startswith("rule ")]
        meta["rule_count"] = len(rules)

    return meta


def _is_relative_to(path: Path, allowed_root: Path) -> bool:
    """Compatibility helper for Path.is_relative_to (Python 3.11+)."""
    if hasattr(path, "is_relative_to"):
        return path.is_relative_to(allowed_root)
    return allowed_root in path.parents or path == allowed_root


def _allowed_roots() -> tuple[Path, ...]:
    """Resolve allowed roots for file reads."""
    cwd = Path.cwd().resolve()
    env_output = os.getenv("BIOPIPE_OUTPUT_DIR")
    output_root = Path(env_output).expanduser().resolve() if env_output else (cwd / "biopipe_output").resolve()
    return (cwd, output_root)


def _is_blocked_system_path(file_path: Path) -> bool:
    """Block sensitive absolute system and SSH config paths."""
    if any(file_path == blocked or _is_relative_to(file_path, blocked) for blocked in _SYSTEM_BLOCKED_PREFIXES):
        return True

    home_ssh = (Path.home() / ".ssh").resolve()
    return file_path == home_ssh or _is_relative_to(file_path, home_ssh)


def _is_allowed_workspace_path(file_path: Path) -> bool:
    """Check whether file path is readable under workspace roots."""
    if _is_blocked_system_path(file_path):
        return False

    return any(_is_relative_to(file_path, allowed_root) for allowed_root in _allowed_roots())


# ── Tool Interface ───────────────────────────────────────────────────────────

class FileReadTool(Tool):
    """Built-in tool: read files with bioinformatics format awareness."""

    name = "file_read"
    description = (
        "Read a file from the local filesystem. Automatically detects bioinformatics "
        "formats (FASTQ, BAM, VCF, BED, GFF, Nextflow, Snakemake) and extracts "
        "relevant metadata. Binary files show headers only. Max 10MB."
    )
    parameter_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute or relative path to the file",
            },
            "max_lines": {
                "type": "integer",
                "description": "Maximum lines to read (default 200)",
                "default": 200,
            },
        },
        "required": ["path"],
    }

    async def execute(self, **params: Any) -> str:
        file_path = Path(params["path"]).expanduser().resolve()
        max_lines = params.get("max_lines", MAX_LINES_PREVIEW)

        if not _is_allowed_workspace_path(file_path):
            return f"ERROR: {ACCESS_DENIED_ERROR}"

        result = read_bio_file(file_path, max_lines=max_lines)

        if "error" in result:
            return f"ERROR: {result['error']}"

        # Format output for LLM
        parts = [f"File: {file_path.name}"]
        parts.append(f"Format: {result['format']}")
        parts.append(f"Size: {result['size_bytes']:,} bytes")

        if result.get("truncated"):
            parts.append(f"Showing {result['lines_read']}/{result['total_lines']} lines")

        if result.get("metadata"):
            for k, v in result["metadata"].items():
                parts.append(f"{k}: {v}")

        # Scrub PHI from output before returning to LLM
        scrubber = PrivacyScrubber()
        parts.append(f"\n--- Content ---\n{scrubber.redact(result['content'])}")

        return "\n".join(parts)
