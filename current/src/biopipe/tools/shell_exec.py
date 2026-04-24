"""Built-in tool: Managed shell execution for bioinformatics.

Runs whitelisted bioinformatics commands with timeout, live streaming,
and safety validation. Blocks arbitrary code execution.
"""

from __future__ import annotations

import asyncio
import subprocess
import shlex
import time
from pathlib import Path
from typing import Any

from biopipe.core.types import Tool
from biopipe.core.safety import SafetyValidator
from biopipe.core.privacy import PrivacyScrubber


# ── Internal Validators ──────────────────────────────────────────────────────


# Only these commands can be executed directly by the agent.
# Everything else requires explicit user permission via /execute.
ALLOWED_COMMANDS = frozenset({
    # QC
    "fastqc", "multiqc", "fastp", "trim_galore", "trimmomatic",
    # Alignment
    "bwa", "bwa-mem2", "hisat2", "bowtie2", "minimap2", "star",
    # SAM/BAM
    "samtools", "sambamba", "picard",
    # Variant Calling
    "bcftools", "gatk", "freebayes", "deepvariant",
    # Utilities
    "bedtools", "tabix", "bgzip", "seqkit", "seqtk",
    # Annotation
    "snpeff", "vep", "annovar",
    # Pipeline
    "nextflow", "snakemake", "cromwell",
    # Data
    "fasterq-dump", "prefetch", "fastq-dump", "wget", "curl",
    # System info (safe)
    "ls", "wc", "head", "tail", "cat", "zcat", "gzip", "gunzip",
    "grep", "awk", "sed", "sort", "uniq", "cut", "tr",
    "du", "df", "free", "uname", "hostname", "module",
    # SLURM
    "squeue", "sinfo", "sacct", "scontrol", "sbatch", "scancel",
    # PBS
    "qstat", "qsub", "qdel", "pbsnodes",
})

# Hard-blocked: never execute these
BLOCKED_COMMANDS = frozenset({
    "rm", "rmdir", "mkfs", "dd", "shutdown", "reboot",
    "chmod", "chown", "su", "sudo", "passwd",
    "curl -X POST", "wget --post",  # block POST requests
    "python", "python3", "pip", "npm", "node",  # block interpreters
})

DEFAULT_TIMEOUT = 300  # 5 minutes
MAX_OUTPUT_SIZE = 50_000  # 50KB output capture


def validate_command(command: str) -> tuple[bool, str]:
    """Validate a shell command against whitelist.

    Returns (allowed, reason).
    """
    if not command.strip():
        return False, "Empty command"

    # Parse first token
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False, "Invalid shell syntax"

    binary = Path(tokens[0]).name  # handle /usr/bin/samtools → samtools

    # Check blocked list
    for blocked in BLOCKED_COMMANDS:
        if blocked in command:
            return False, f"Blocked command: {blocked}"

    # Check whitelist
    if binary not in ALLOWED_COMMANDS:
        return False, (
            f"Command '{binary}' is not in the bioinformatics whitelist. "
            f"Use /execute to run arbitrary commands with permission."
        )

    return True, "OK"


async def run_command(
    command: str,
    cwd: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    stream_callback: Any = None,
) -> dict[str, Any]:
    """Execute a whitelisted command with timeout and output capture.

    Args:
        command: Shell command to run.
        cwd: Working directory.
        timeout: Max execution time in seconds.
        stream_callback: Optional callback(line: str) for live output.

    Returns:
        Dict with: stdout, stderr, exit_code, elapsed, truncated.
    """
    allowed, reason = validate_command(command)
    if not allowed:
        return {
            "error": reason,
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
            "elapsed": 0,
        }

    # Core Safety Layer: Validate against malicious patterns, eval, obfuscation, networking
    validator = SafetyValidator()
    report = validator.validate(command)
    if not report.passed:
        violations = ", ".join([v.description for v in report.violations if v.severity == "critical"])
        return {
            "error": f"Core Safety Violation: Command blocked due to security rules ({violations})",
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
            "elapsed": 0,
        }

    start = time.monotonic()

    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )

        stdout_parts = []
        stderr_parts = []
        total_output = 0

        async def _read_stream(stream, parts, is_stdout=True):
            nonlocal total_output
            while True:
                line = await stream.readline()
                if not line:
                    break
                decoded = line.decode("utf-8", errors="replace")
                total_output += len(decoded)

                if total_output <= MAX_OUTPUT_SIZE:
                    parts.append(decoded)
                    if stream_callback and is_stdout:
                        stream_callback(decoded)

        try:
            await asyncio.wait_for(
                asyncio.gather(
                    _read_stream(process.stdout, stdout_parts, True),
                    _read_stream(process.stderr, stderr_parts, False),
                ),
                timeout=timeout,
            )
            await process.wait()
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return {
                "stdout": "".join(stdout_parts),
                "stderr": f"TIMEOUT: Command exceeded {timeout}s limit",
                "exit_code": -1,
                "elapsed": time.monotonic() - start,
                "truncated": total_output > MAX_OUTPUT_SIZE,
                "timed_out": True,
            }

        # Scrub PHI from output before returning to LLM
        scrubber = PrivacyScrubber()
        return {
            "stdout": scrubber.redact("".join(stdout_parts)),
            "stderr": scrubber.redact("".join(stderr_parts)),
            "exit_code": process.returncode,
            "elapsed": time.monotonic() - start,
            "truncated": total_output > MAX_OUTPUT_SIZE,
        }

    except Exception as e:
        return {
            "error": str(e),
            "stdout": "",
            "stderr": PrivacyScrubber().redact(str(e)),
            "exit_code": -1,
            "elapsed": time.monotonic() - start,
        }



# ── Tool Interface ───────────────────────────────────────────────────────────

class ShellExecTool(Tool):
    """Built-in tool: execute whitelisted bioinformatics commands."""

    name = "shell_exec"
    description = (
        "Execute a bioinformatics shell command (samtools, bcftools, fastqc, bwa, "
        "gatk, nextflow, snakemake, squeue, etc.). Only whitelisted bioinformatics "
        "tools are allowed. Arbitrary code is blocked for safety. "
        "Use this to run QC, alignment, variant calling, and cluster commands."
    )
    parameter_schema = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Shell command to execute (e.g., 'samtools flagstat input.bam')",
            },
            "cwd": {
                "type": "string",
                "description": "Working directory (optional)",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default 300)",
                "default": 300,
            },
        },
        "required": ["command"],
    }

    async def execute(self, **params: Any) -> str:
        result = await run_command(
            command=params["command"],
            cwd=params.get("cwd"),
            timeout=params.get("timeout", DEFAULT_TIMEOUT),
        )

        if "error" in result:
            return f"ERROR: {result['error']}"

        parts = []
        if result["exit_code"] == 0:
            parts.append(f"✓ Command succeeded ({result['elapsed']:.1f}s)")
        else:
            parts.append(f"✗ Command failed (exit code {result['exit_code']}, {result['elapsed']:.1f}s)")

        if result.get("timed_out"):
            parts.append("⚠ TIMED OUT")
        if result.get("truncated"):
            parts.append("⚠ Output truncated (>50KB)")

        if result["stdout"]:
            parts.append(f"\n--- stdout ---\n{result['stdout']}")
        if result["stderr"] and result["exit_code"] != 0:
            parts.append(f"\n--- stderr ---\n{result['stderr']}")

        return "\n".join(parts)
