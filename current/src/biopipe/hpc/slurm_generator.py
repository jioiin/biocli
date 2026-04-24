"""SLURM Script Generator: wraps pipelines in HPC job scripts.

Takes a pipeline script + cluster profile and generates optimized
SLURM job submission scripts with correct partitions, module loads,
GPU allocation, and time limits.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from biopipe.hpc.cluster_profiler import ClusterProfile, Partition


@dataclass
class SLURMConfig:
    """SLURM job configuration."""
    job_name: str = "biopipe_job"
    partition: str = ""
    nodes: int = 1
    ntasks: int = 1
    cpus_per_task: int = 4
    mem_gb: int = 16
    time: str = "24:00:00"
    gpu_type: str = ""
    gpu_count: int = 0
    account: str = ""
    output: str = "slurm_%j.out"
    error: str = "slurm_%j.err"
    mail_type: str = "END,FAIL"
    mail_user: str = ""
    modules: list[str] | None = None
    container: str = ""  # Singularity image
    extra_sbatch: list[str] | None = None


# ── Resource estimator ───────────────────────────────────────────────────────

# Estimated resource requirements per bioinformatics tool
TOOL_RESOURCES = {
    "bwa": {"cpus": 8, "mem_gb": 16, "time_h": 4, "gpu": False},
    "bwa-mem2": {"cpus": 8, "mem_gb": 24, "time_h": 3, "gpu": False},
    "star": {"cpus": 8, "mem_gb": 32, "time_h": 6, "gpu": False},
    "hisat2": {"cpus": 4, "mem_gb": 8, "time_h": 2, "gpu": False},
    "bowtie2": {"cpus": 4, "mem_gb": 8, "time_h": 3, "gpu": False},
    "samtools": {"cpus": 4, "mem_gb": 4, "time_h": 1, "gpu": False},
    "gatk": {"cpus": 4, "mem_gb": 16, "time_h": 8, "gpu": False},
    "deepvariant": {"cpus": 8, "mem_gb": 32, "time_h": 4, "gpu": True},
    "fastqc": {"cpus": 2, "mem_gb": 4, "time_h": 1, "gpu": False},
    "multiqc": {"cpus": 1, "mem_gb": 4, "time_h": 0.5, "gpu": False},
    "fastp": {"cpus": 4, "mem_gb": 4, "time_h": 1, "gpu": False},
    "trimmomatic": {"cpus": 4, "mem_gb": 4, "time_h": 2, "gpu": False},
    "bcftools": {"cpus": 2, "mem_gb": 4, "time_h": 1, "gpu": False},
    "freebayes": {"cpus": 1, "mem_gb": 8, "time_h": 12, "gpu": False},
    "salmon": {"cpus": 8, "mem_gb": 16, "time_h": 2, "gpu": False},
    "kallisto": {"cpus": 4, "mem_gb": 8, "time_h": 1, "gpu": False},
    "picard": {"cpus": 2, "mem_gb": 16, "time_h": 2, "gpu": False},
}


def estimate_resources(script: str) -> dict[str, Any]:
    """Estimate resource requirements from a pipeline script."""
    cpus = 4
    mem_gb = 8
    time_h = 2.0
    needs_gpu = False

    for tool, reqs in TOOL_RESOURCES.items():
        if tool in script.lower():
            cpus = max(cpus, reqs["cpus"])
            mem_gb = max(mem_gb, reqs["mem_gb"])
            time_h = max(time_h, reqs["time_h"])
            if reqs["gpu"]:
                needs_gpu = True

    return {
        "cpus": cpus,
        "mem_gb": mem_gb,
        "time_hours": time_h,
        "needs_gpu": needs_gpu,
    }


# ── Generator ────────────────────────────────────────────────────────────────

class SLURMGenerator:
    """Generate SLURM job scripts from pipelines + cluster profile."""

    def generate(
        self,
        script: str,
        profile: ClusterProfile,
        config: SLURMConfig | None = None,
    ) -> str:
        """Generate a complete SLURM submission script.

        Args:
            script: The pipeline script to wrap.
            profile: Detected cluster profile.
            config: Optional manual configuration overrides.

        Returns:
            Complete SLURM script as string.
        """
        # Auto-estimate resources if no config
        if config is None:
            est = estimate_resources(script)
            config = SLURMConfig(
                cpus_per_task=est["cpus"],
                mem_gb=est["mem_gb"],
                time=f"{int(est['time_hours'])}:00:00",
            )
            if est["needs_gpu"]:
                config.gpu_count = 1

        # Resolve partition
        if not config.partition and profile.partitions:
            config.partition = self._select_partition(profile, config)

        # Resolve account
        if not config.account and profile.account:
            config.account = profile.account

        # Resolve modules
        if config.modules is None:
            config.modules = self._detect_modules(script, profile)

        return self._render(script, config, profile)

    def _select_partition(self, profile: ClusterProfile, config: SLURMConfig) -> str:
        """Select best partition for the job."""
        # If GPU needed, find GPU partition
        if config.gpu_count > 0:
            for p in profile.partitions:
                if p.gpus and p.state == "up":
                    return p.name

        # Use default partition
        if profile.default_partition:
            return profile.default_partition

        # First available
        for p in profile.partitions:
            if p.state == "up":
                return p.name

        return "compute"  # fallback

    def _detect_modules(self, script: str, profile: ClusterProfile) -> list[str]:
        """Auto-detect which modules to load based on script content."""
        needed = []
        script_lower = script.lower()

        for mod in profile.bio_modules:
            mod_base = mod.split("/")[0].lower()
            if mod_base in script_lower:
                needed.append(mod)

        return needed

    def _render(self, script: str, config: SLURMConfig, profile: ClusterProfile) -> str:
        """Render the final SLURM script."""
        lines = ["#!/bin/bash"]
        lines.append(f"#SBATCH --job-name={config.job_name}")

        if config.partition:
            lines.append(f"#SBATCH --partition={config.partition}")
        if config.account:
            lines.append(f"#SBATCH --account={config.account}")

        lines.append(f"#SBATCH --nodes={config.nodes}")
        lines.append(f"#SBATCH --ntasks={config.ntasks}")
        lines.append(f"#SBATCH --cpus-per-task={config.cpus_per_task}")
        lines.append(f"#SBATCH --mem={config.mem_gb}G")
        lines.append(f"#SBATCH --time={config.time}")
        lines.append(f"#SBATCH --output={config.output}")
        lines.append(f"#SBATCH --error={config.error}")

        if config.gpu_count > 0:
            if config.gpu_type:
                lines.append(f"#SBATCH --gres=gpu:{config.gpu_type}:{config.gpu_count}")
            else:
                lines.append(f"#SBATCH --gres=gpu:{config.gpu_count}")

        if config.mail_type and config.mail_user:
            lines.append(f"#SBATCH --mail-type={config.mail_type}")
            lines.append(f"#SBATCH --mail-user={config.mail_user}")

        if config.extra_sbatch:
            for extra in config.extra_sbatch:
                lines.append(f"#SBATCH {extra}")

        lines.append("")
        lines.append("# ── Environment ──────────────────────────────────────────")
        lines.append("set -euo pipefail")
        lines.append("")

        # Module loads
        if config.modules:
            for mod in config.modules:
                lines.append(f"module load {mod}")
            lines.append("")

        # Singularity / Container
        if config.container:
            lines.append(f"CONTAINER=\"{config.container}\"")
            lines.append("")

        # Scratch directory
        if profile.scratch_dir:
            lines.append(f"SCRATCH=\"{profile.scratch_dir}/$SLURM_JOB_ID\"")
            lines.append("mkdir -p $SCRATCH")
            lines.append("")

        lines.append("# ── Pipeline ─────────────────────────────────────────────")
        lines.append("echo \"Job started: $(date)\"")
        lines.append(f"echo \"Running on: $(hostname)\"")
        lines.append(f"echo \"CPUs: $SLURM_CPUS_PER_TASK\"")
        lines.append("")

        # Inject the actual pipeline
        lines.append(script)

        lines.append("")
        lines.append("echo \"Job completed: $(date)\"")

        # Cleanup scratch
        if profile.scratch_dir:
            lines.append("")
            lines.append("# Cleanup scratch")
            lines.append("# rm -rf $SCRATCH  # uncomment to auto-cleanup")

        return "\n".join(lines)
