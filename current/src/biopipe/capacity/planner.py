"""Local Cluster Capacity Planner: estimate HPC resources natively.

Calculates how many CPU-hours, GPU-hours, and exact terabytes of
storage are required to run a pipeline locally on the university cluster.
Designed 100% for air-gapped grids. No cloud APIs, completely local.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CapacityEstimate:
    """Estimated local resource footprint for a pipeline."""
    pipeline: str
    samples: int
    total_cpu_hours: int
    total_gpu_hours: int
    storage_tb_required: float
    nodes_recommended: int
    time_estimate_days: float


# Per-sample resource estimates (100% local HPC modeling)
PIPELINE_PROFILES = {
    "wgs": {
        "description": "Whole Genome Sequencing (30x)",
        "cpu_hours_per_sample": 80,
        "gpu_hours_per_sample": 2,      # Local DeepVariant
        "storage_gb_per_sample": 200,   # FASTQ + BAM + VCF
    },
    "wgs_low": {
        "description": "Whole Genome Sequencing (10x)",
        "cpu_hours_per_sample": 30,
        "gpu_hours_per_sample": 1,
        "storage_gb_per_sample": 80,
    },
    "wes": {
        "description": "Whole Exome Sequencing",
        "cpu_hours_per_sample": 15,
        "gpu_hours_per_sample": 0.5,
        "storage_gb_per_sample": 30,
    },
    "rnaseq": {
        "description": "RNA-seq (quantification + DE)",
        "cpu_hours_per_sample": 8,
        "gpu_hours_per_sample": 0,
        "storage_gb_per_sample": 20,
    },
    "chipseq": {
        "description": "ChIP-seq (peak calling)",
        "cpu_hours_per_sample": 6,
        "gpu_hours_per_sample": 0,
        "storage_gb_per_sample": 15,
    },
    "atacseq": {
        "description": "ATAC-seq",
        "cpu_hours_per_sample": 5,
        "gpu_hours_per_sample": 0,
        "storage_gb_per_sample": 10,
    },
    "methylation": {
        "description": "Bisulfite/Methylation sequencing",
        "cpu_hours_per_sample": 40,
        "gpu_hours_per_sample": 0,
        "storage_gb_per_sample": 100,
    },
}


class CapacityPlanner:
    """Predicts local cluster footprint without internet assumptions."""

    def estimate(
        self,
        pipeline_type: str,
        num_samples: int,
        cluster_cpus_available: int = 128,  # Default university standard node count
    ) -> CapacityEstimate:
        """Estimate required resources based on local grid capacity."""
        profile = PIPELINE_PROFILES.get(pipeline_type.lower())
        if not profile:
            available = ", ".join(sorted(PIPELINE_PROFILES.keys()))
            raise ValueError(
                f"Unknown pipeline pattern '{pipeline_type}'. Available: {available}"
            )

        total_cpu = int(profile["cpu_hours_per_sample"] * num_samples)
        total_gpu = int(profile["gpu_hours_per_sample"] * num_samples)
        storage_tb = (profile["storage_gb_per_sample"] * num_samples) / 1024.0

        # Heuristic for days to complete based on concurrency assumption
        # Assume we can use cluster_cpus_available in parallel at 80% efficiency
        actual_parallel_power = max(1, int(cluster_cpus_available * 0.8))
        days = total_cpu / actual_parallel_power / 24.0

        return CapacityEstimate(
            pipeline=profile["description"],
            samples=num_samples,
            total_cpu_hours=total_cpu,
            total_gpu_hours=total_gpu,
            storage_tb_required=storage_tb,
            nodes_recommended=max(1, total_cpu // 72),  # Roughly 72-hour node cycles
            time_estimate_days=round(days, 1),
        )

    def format_estimate(self, est: CapacityEstimate) -> str:
        """Format the capacity assessment for terminal output."""
        lines = [
            f"=== Local Cluster Capacity Plan ===",
            f"Pipeline:    {est.pipeline}",
            f"Cohort Size: {est.samples} samples",
            f"-----------------------------------",
            f"Compute:     {est.total_cpu_hours:,} CPU-hours",
        ]
        if est.total_gpu_hours > 0:
            lines.append(f"GPU Compute: {est.total_gpu_hours:,} GPU-hours")
        
        lines.extend([
            f"Storage:     {est.storage_tb_required:.2f} TB required on local scratch",
            f"Time to run: ~{est.time_estimate_days} days (assuming 128 CPU continuous availability)",
            f"Status:      100% AIR-GAPPED READY. No external APIs."
        ])
        return "\n".join(lines)
