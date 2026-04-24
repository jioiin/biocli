"""System profiler: detect local environment capabilities.

All checks are local: subprocess calls to `which`, `nproc`, `free`.
No network. No API. No telemetry.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ToolStatus:
    """Whether a bioinformatics tool is installed."""
    name: str
    installed: bool
    path: str | None = None
    version: str | None = None


@dataclass
class SystemProfile:
    """Local system capabilities."""
    cpu_count: int = 0
    ram_gb: float = 0.0
    disk_free_gb: float = 0.0
    os_name: str = ""
    hostname: str = ""
    tools: list[ToolStatus] = field(default_factory=list)
    slurm_available: bool = False
    singularity_available: bool = False
    conda_available: bool = False

    def format_for_llm(self) -> str:
        """Format system profile for LLM context."""
        installed = [t for t in self.tools if t.installed]
        missing = [t for t in self.tools if not t.installed]
        parts = [
            "<system_profile>",
            f"OS: {self.os_name} | Host: {self.hostname}",
            f"CPU: {self.cpu_count} cores | RAM: {self.ram_gb:.1f} GB | Disk free: {self.disk_free_gb:.1f} GB",
            f"SLURM: {'yes' if self.slurm_available else 'no'} | "
            f"Singularity: {'yes' if self.singularity_available else 'no'} | "
            f"Conda: {'yes' if self.conda_available else 'no'}",
        ]
        if installed:
            parts.append(f"Installed tools ({len(installed)}): {', '.join(t.name for t in installed)}")
        if missing:
            parts.append(f"Missing tools ({len(missing)}): {', '.join(t.name for t in missing)}")
        parts.append("</system_profile>")
        return "\n".join(parts)

    def recommended_threads(self) -> int:
        """Suggest thread count: 75% of available CPUs."""
        return max(1, int(self.cpu_count * 0.75))


# Tools to check for
_TOOLS_TO_CHECK: list[str] = [
    "fastqc", "fastp", "trimmomatic", "cutadapt",
    "bwa", "bowtie2", "hisat2", "star", "minimap2",
    "samtools", "bcftools", "bedtools", "picard",
    "gatk", "freebayes",
    "featurecounts", "stringtie", "salmon", "kallisto",
    "macs2", "multiqc",
    "snpeff", "vep",
    "singularity", "apptainer", "docker",
    "nextflow", "snakemake",
    "python3", "R", "Rscript",
]


class SystemProfiler:
    """Profile local system: CPU, RAM, installed tools."""

    def profile(self) -> SystemProfile:
        """Run all checks and return SystemProfile."""
        p = SystemProfile()
        p.cpu_count = os.cpu_count() or 1
        p.ram_gb = self._get_ram_gb()
        p.disk_free_gb = self._get_disk_free_gb()
        p.os_name = self._get_os()
        p.hostname = self._get_hostname()
        p.tools = [self._check_tool(name) for name in _TOOLS_TO_CHECK]
        p.slurm_available = self._cmd_exists("squeue")
        p.singularity_available = self._cmd_exists("singularity") or self._cmd_exists("apptainer")
        p.conda_available = self._cmd_exists("conda")
        return p

    def _check_tool(self, name: str) -> ToolStatus:
        """Check if a tool is installed and get its version."""
        path = shutil.which(name)
        if not path:
            return ToolStatus(name=name, installed=False)

        version = self._get_version(name)
        return ToolStatus(name=name, installed=True, path=path, version=version)

    @staticmethod
    def _get_version(name: str) -> str | None:
        """Try to get version string."""
        for flag in ["--version", "-version", "-v"]:
            try:
                r = subprocess.run(
                    [name, flag], capture_output=True, text=True, timeout=5
                )
                output = (r.stdout or r.stderr).strip()
                if output:
                    return output.split("\n")[0][:100]
            except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
                continue
        return None

    @staticmethod
    def _get_ram_gb() -> float:
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal"):
                        kb = int(line.split()[1])
                        return kb / 1024 / 1024
        except (FileNotFoundError, ValueError):
            pass
        return 0.0

    @staticmethod
    def _get_disk_free_gb() -> float:
        try:
            import shutil
            usage = shutil.disk_usage(".")
            return usage.free / (1024 ** 3)
        except OSError:
            return 0.0

    @staticmethod
    def _get_os() -> str:
        try:
            r = subprocess.run(["uname", "-sr"], capture_output=True, text=True, timeout=5)
            return r.stdout.strip() if r.returncode == 0 else "unknown"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return "unknown"

    @staticmethod
    def _get_hostname() -> str:
        try:
            r = subprocess.run(["hostname"], capture_output=True, text=True, timeout=5)
            return r.stdout.strip() if r.returncode == 0 else "unknown"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return "unknown"

    @staticmethod
    def _cmd_exists(name: str) -> bool:
        return shutil.which(name) is not None
