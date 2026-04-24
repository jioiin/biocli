"""Error recovery: diagnose script failures and suggest fixes.

When a script fails during execution, this module:
1. Parses stderr for known error patterns
2. Maps errors to bioinformatics-specific causes
3. Suggests concrete fixes
All local — no API calls.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Diagnosis:
    """Diagnosed error with suggested fix."""
    tool: str
    error_type: str
    description: str
    suggestion: str
    stderr_line: str


# Pattern → (tool, error_type, description, suggestion)
_ERROR_PATTERNS: list[tuple[str, str, str, str, str]] = [
    # FastQC
    (r"Failed to process file (\S+)",
     "fastqc", "file_not_found", "FastQC cannot find input file",
     "Check file path and ensure FASTQ files exist"),

    # BWA
    (r"\[bwa_index\] fail to open file '(\S+)'",
     "bwa", "missing_index", "BWA reference index not found",
     "Run: bwa index {reference.fa} before alignment"),
    (r"fail to locate the index",
     "bwa", "missing_index", "BWA index files not found",
     "Run: bwa index {reference.fa}"),

    # samtools
    (r"\[E::hts_open_format\] Failed to open \"(\S+)\"",
     "samtools", "file_not_found", "samtools cannot open input file",
     "Check that the BAM/SAM file exists and path is correct"),
    (r"is not sorted",
     "samtools", "unsorted", "BAM file is not sorted",
     "Add: samtools sort before this step"),

    # GATK
    (r"A USER ERROR has occurred: (\S+) not found",
     "gatk", "missing_file", "GATK cannot find required file",
     "Check that reference .fa, .fai, and .dict files all exist"),
    (r"Read group .* not found",
     "gatk", "missing_read_group", "BAM missing Read Group (@RG)",
     "Add -R \"@RG\\tID:sample\\tSM:sample\\tPL:ILLUMINA\" to bwa mem"),
    (r"requires a sequence dictionary",
     "gatk", "missing_dict", "Reference genome .dict file missing",
     "Run: gatk CreateSequenceDictionary -R reference.fa"),

    # HISAT2
    (r"Could not locate a HISAT2 index",
     "hisat2", "missing_index", "HISAT2 index not found",
     "Run: hisat2-build reference.fa genome_index"),

    # General
    (r"command not found",
     "system", "tool_missing", "Required tool is not installed",
     "Install via conda/module load, or check PATH"),
    (r"No space left on device",
     "system", "disk_full", "Disk is full",
     "Free disk space or change output directory"),
    (r"Permission denied",
     "system", "permission", "Insufficient file permissions",
     "Check directory permissions: ls -la"),
    (r"Killed|Out of memory|Cannot allocate memory",
     "system", "oom", "Process killed — out of memory",
     "Reduce threads or request more memory in SLURM: --mem=64G"),
    (r"SBATCH: error: .* Partition .* not available",
     "slurm", "bad_partition", "SLURM partition does not exist",
     "Check available partitions: sinfo -s"),
]


class ErrorRecovery:
    """Parse stderr and diagnose bioinformatics pipeline errors."""

    def diagnose(self, stderr: str) -> list[Diagnosis]:
        """Analyze stderr for known error patterns.

        Args:
            stderr: Standard error output from failed script.

        Returns:
            List of diagnosed errors with suggestions.
        """
        diagnoses: list[Diagnosis] = []
        seen: set[str] = set()

        for line in stderr.split("\n"):
            for pattern, tool, err_type, desc, suggestion in _ERROR_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    key = f"{tool}:{err_type}"
                    if key not in seen:
                        seen.add(key)
                        diagnoses.append(Diagnosis(
                            tool=tool,
                            error_type=err_type,
                            description=desc,
                            suggestion=suggestion,
                            stderr_line=line.strip()[:200],
                        ))

        return diagnoses

    def format_report(self, diagnoses: list[Diagnosis]) -> str:
        """Format diagnoses as human-readable report."""
        if not diagnoses:
            return "No known error patterns found. Check stderr manually."

        lines = [f"Found {len(diagnoses)} issue(s):\n"]
        for i, d in enumerate(diagnoses, 1):
            lines.append(f"  {i}. [{d.tool}] {d.description}")
            lines.append(f"     Fix: {d.suggestion}")
            lines.append(f"     stderr: {d.stderr_line}")
            lines.append("")
        return "\n".join(lines)
