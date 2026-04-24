"""HPC Cluster Profiler: auto-detect SLURM/PBS/SGE environment.

Scans the host system to determine which HPC scheduler is available,
what queues/partitions exist, available modules, GPU resources, and
account limits. This information is injected into the LLM context
so generated scripts match the user's actual cluster.
"""

from __future__ import annotations

import os
import subprocess
import shutil
from dataclasses import dataclass, field
from typing import Any


@dataclass
class GPUInfo:
    """GPU resource info on a cluster node."""
    gpu_type: str = ""       # e.g. "a100", "v100", "rtx3090"
    count: int = 0
    memory_gb: float = 0.0


@dataclass
class Partition:
    """A SLURM partition / PBS queue."""
    name: str
    state: str = "up"
    max_time: str = ""
    nodes: int = 0
    cpus_per_node: int = 0
    gpus: list[GPUInfo] = field(default_factory=list)
    default: bool = False


@dataclass
class ClusterProfile:
    """Complete profile of the detected HPC environment."""
    scheduler: str = "none"  # slurm | pbs | sge | none
    hostname: str = ""
    partitions: list[Partition] = field(default_factory=list)
    available_modules: list[str] = field(default_factory=list)
    bio_modules: list[str] = field(default_factory=list)
    account: str = ""
    max_jobs: int = 0
    default_partition: str = ""
    scratch_dir: str = ""
    has_singularity: bool = False
    has_docker: bool = False
    has_conda: bool = False

    def to_context(self) -> str:
        """Format profile for injection into LLM system prompt."""
        if self.scheduler == "none":
            return "No HPC scheduler detected (local workstation)."

        lines = [
            f"HPC Cluster: {self.hostname}",
            f"Scheduler: {self.scheduler.upper()}",
        ]

        if self.partitions:
            lines.append("Partitions:")
            for p in self.partitions:
                gpu_str = ""
                if p.gpus:
                    gpu_str = f", GPU: {p.gpus[0].count}x {p.gpus[0].gpu_type}"
                default = " (DEFAULT)" if p.default else ""
                lines.append(
                    f"  - {p.name}: {p.nodes} nodes, {p.cpus_per_node} CPUs/node"
                    f"{gpu_str}, max {p.max_time}{default}"
                )

        if self.bio_modules:
            lines.append(f"Bio modules: {', '.join(self.bio_modules[:20])}")

        if self.account:
            lines.append(f"Account: {self.account}")
        if self.scratch_dir:
            lines.append(f"Scratch: {self.scratch_dir}")

        container = []
        if self.has_singularity:
            container.append("Singularity")
        if self.has_docker:
            container.append("Docker")
        if container:
            lines.append(f"Containers: {', '.join(container)}")

        return "\n".join(lines)


class ClusterProfiler:
    """Auto-detect HPC cluster environment."""

    # Known bioinformatics module patterns
    BIO_MODULE_PATTERNS = [
        "samtools", "bwa", "bowtie", "hisat", "star", "minimap",
        "gatk", "bcftools", "bedtools", "picard", "fastqc", "multiqc",
        "trimmomatic", "fastp", "trim_galore", "cutadapt",
        "nextflow", "snakemake", "singularity", "apptainer",
        "r/", "R/", "python/", "java/", "conda",
        "deepvariant", "freebayes", "varscan",
        "salmon", "kallisto", "rsem", "subread", "featurecounts",
    ]

    def detect(self) -> ClusterProfile:
        """Run full cluster detection."""
        profile = ClusterProfile()
        profile.hostname = self._get_hostname()

        # Detect scheduler
        if shutil.which("sinfo"):
            profile.scheduler = "slurm"
            self._detect_slurm(profile)
        elif shutil.which("qstat"):
            profile.scheduler = "pbs"
            self._detect_pbs(profile)
        elif shutil.which("qconf"):
            profile.scheduler = "sge"

        # Common detection
        self._detect_modules(profile)
        self._detect_containers(profile)
        self._detect_scratch(profile)
        profile.has_conda = shutil.which("conda") is not None

        return profile

    def _get_hostname(self) -> str:
        try:
            result = subprocess.run(
                ["hostname"], capture_output=True, text=True, timeout=5,
            )
            return result.stdout.strip()
        except Exception:
            return os.environ.get("HOSTNAME", "unknown")

    def _detect_slurm(self, profile: ClusterProfile) -> None:
        """Detect SLURM partitions, GPUs, and account."""
        # sinfo -N -o "%P %a %l %D %c %G"
        try:
            result = subprocess.run(
                ["sinfo", "--noheader", "-o", "%P %a %l %D %c %G"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                seen = set()
                for line in result.stdout.strip().splitlines():
                    parts = line.split()
                    if len(parts) >= 5:
                        name = parts[0].rstrip("*")
                        is_default = parts[0].endswith("*")
                        if name in seen:
                            continue
                        seen.add(name)

                        gpus = []
                        if len(parts) >= 6 and parts[5] != "(null)":
                            # Parse "gpu:a100:4"
                            gpu_parts = parts[5].split(":")
                            if len(gpu_parts) >= 3:
                                gpus.append(GPUInfo(
                                    gpu_type=gpu_parts[1],
                                    count=int(gpu_parts[2]) if gpu_parts[2].isdigit() else 0,
                                ))
                            elif len(gpu_parts) == 2 and gpu_parts[1].isdigit():
                                gpus.append(GPUInfo(count=int(gpu_parts[1])))

                        partition = Partition(
                            name=name,
                            state=parts[1],
                            max_time=parts[2],
                            nodes=int(parts[3]) if parts[3].isdigit() else 0,
                            cpus_per_node=int(parts[4]) if parts[4].isdigit() else 0,
                            gpus=gpus,
                            default=is_default,
                        )
                        profile.partitions.append(partition)
                        if is_default:
                            profile.default_partition = name
        except Exception:
            pass

        # Detect account
        try:
            result = subprocess.run(
                ["sacctmgr", "show", "assoc", f"user={os.environ.get('USER', '')}", "-nP", "-o", "Account"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                profile.account = result.stdout.strip().splitlines()[0]
        except Exception:
            pass

    def _detect_pbs(self, profile: ClusterProfile) -> None:
        """Detect PBS/Torque queues."""
        try:
            result = subprocess.run(
                ["qstat", "-Q"], capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                for line in result.stdout.strip().splitlines()[2:]:  # skip header
                    parts = line.split()
                    if parts:
                        profile.partitions.append(Partition(
                            name=parts[0],
                            state="enabled" if len(parts) > 2 and parts[2] == "yes" else "disabled",
                        ))
        except Exception:
            pass

    def _detect_modules(self, profile: ClusterProfile) -> None:
        """Detect available environment modules."""
        try:
            # `module avail` outputs to stderr on most systems
            result = subprocess.run(
                ["bash", "-c", "module avail 2>&1 | head -200"],
                capture_output=True, text=True, timeout=15,
                env={**os.environ, "MODULEPATH": os.environ.get("MODULEPATH", "")},
            )
            if result.returncode == 0:
                # Parse module names from output
                for line in result.stdout.splitlines():
                    for token in line.split():
                        clean = token.strip().rstrip("/")
                        if clean and not clean.startswith("-"):
                            profile.available_modules.append(clean)

                # Filter bio-related modules
                for mod in profile.available_modules:
                    mod_lower = mod.lower()
                    for pattern in self.BIO_MODULE_PATTERNS:
                        if pattern in mod_lower:
                            profile.bio_modules.append(mod)
                            break
        except Exception:
            pass

    def _detect_containers(self, profile: ClusterProfile) -> None:
        """Check for Singularity/Apptainer and Docker."""
        profile.has_singularity = (
            shutil.which("singularity") is not None
            or shutil.which("apptainer") is not None
        )
        profile.has_docker = shutil.which("docker") is not None

    def _detect_scratch(self, profile: ClusterProfile) -> None:
        """Detect common scratch directories."""
        candidates = [
            os.environ.get("SCRATCH", ""),
            os.environ.get("TMPDIR", ""),
            f"/scratch/{os.environ.get('USER', '')}",
            f"/lustre/scratch/{os.environ.get('USER', '')}",
            f"/work/{os.environ.get('USER', '')}",
        ]
        for path in candidates:
            if path and os.path.isdir(path):
                profile.scratch_dir = path
                break
