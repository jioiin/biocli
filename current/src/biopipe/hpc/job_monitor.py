"""HPC Job Monitor: track and analyze SLURM/PBS jobs.

Provides job listing, status checking, and AI-assisted
error analysis for failed jobs.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Any

from biopipe.core.privacy import PrivacyScrubber


@dataclass
class JobInfo:
    """Information about an HPC job."""
    job_id: str
    name: str = ""
    state: str = ""
    partition: str = ""
    elapsed: str = ""
    node: str = ""
    exit_code: str = ""
    submit_time: str = ""
    start_time: str = ""
    end_time: str = ""


class JobMonitor:
    """Monitor HPC jobs (SLURM and PBS)."""

    def list_jobs(self, user: str = "", scheduler: str = "slurm") -> list[JobInfo]:
        """List active/recent jobs for a user."""
        if scheduler == "slurm":
            return self._slurm_list(user)
        elif scheduler == "pbs":
            return self._pbs_list(user)
        return []

    def job_status(self, job_id: str, scheduler: str = "slurm") -> JobInfo | None:
        """Get detailed status for a specific job."""
        if scheduler == "slurm":
            return self._slurm_status(job_id)
        elif scheduler == "pbs":
            return self._pbs_status(job_id)
        return None

    def job_log(self, job_id: str, lines: int = 50) -> str:
        """Read the tail of a SLURM job's output log."""
        import glob
        import os

        # Common SLURM output patterns
        patterns = [
            f"slurm_{job_id}.out",
            f"slurm-{job_id}.out",
            f"*_{job_id}.out",
        ]

        for pattern in patterns:
            matches = glob.glob(pattern)
            if matches:
                try:
                    with open(matches[0], "r", errors="replace") as f:
                        all_lines = f.readlines()
                        content = "".join(all_lines[-lines:])
                        return PrivacyScrubber().redact(content)
                except Exception:
                    pass

        return f"No log file found for job {job_id}"

    def format_jobs_table(self, jobs: list[JobInfo]) -> str:
        """Format jobs as a readable table."""
        if not jobs:
            return "No jobs found."

        lines = [
            f"{'ID':<12} {'Name':<20} {'State':<12} {'Partition':<12} {'Elapsed':<12} {'Node'}",
            "─" * 80,
        ]
        for j in jobs:
            state_icon = {"RUNNING": "🟢", "PENDING": "🟡", "COMPLETED": "✅", "FAILED": "❌"}.get(j.state, "⚪")
            lines.append(
                f"{j.job_id:<12} {j.name:<20} {state_icon} {j.state:<10} {j.partition:<12} {j.elapsed:<12} {j.node}"
            )

        return "\n".join(lines)

    # ── SLURM ────────────────────────────────────────────────────────────

    def _slurm_list(self, user: str) -> list[JobInfo]:
        """List SLURM jobs using squeue + sacct."""
        jobs = []

        # Active jobs via squeue
        try:
            cmd = ["squeue", "--noheader", "-o", "%i %j %T %P %M %N"]
            if user:
                cmd.extend(["-u", user])

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                for line in result.stdout.strip().splitlines():
                    parts = line.split(maxsplit=5)
                    if len(parts) >= 4:
                        jobs.append(JobInfo(
                            job_id=parts[0],
                            name=parts[1] if len(parts) > 1 else "",
                            state=parts[2] if len(parts) > 2 else "",
                            partition=parts[3] if len(parts) > 3 else "",
                            elapsed=parts[4] if len(parts) > 4 else "",
                            node=parts[5] if len(parts) > 5 else "",
                        ))
        except Exception:
            pass

        # Recent completed/failed jobs via sacct (last 24h)
        try:
            cmd = [
                "sacct", "--noheader", "-S", "now-24hours",
                "-o", "JobID,JobName,State,Partition,Elapsed,NodeList,ExitCode",
                "--parsable2",
            ]
            if user:
                cmd.extend(["-u", user])

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                seen_ids = {j.job_id for j in jobs}
                for line in result.stdout.strip().splitlines():
                    parts = line.split("|")
                    if len(parts) >= 5:
                        # Skip sub-steps (e.g. "12345.batch")
                        job_id = parts[0]
                        if "." in job_id or job_id in seen_ids:
                            continue
                        jobs.append(JobInfo(
                            job_id=job_id,
                            name=parts[1],
                            state=parts[2],
                            partition=parts[3],
                            elapsed=parts[4],
                            node=parts[5] if len(parts) > 5 else "",
                            exit_code=parts[6] if len(parts) > 6 else "",
                        ))
        except Exception:
            pass

        return jobs

    def _slurm_status(self, job_id: str) -> JobInfo | None:
        """Get detailed SLURM job info."""
        try:
            result = subprocess.run(
                ["scontrol", "show", "job", job_id],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                info = JobInfo(job_id=job_id)
                for line in result.stdout.splitlines():
                    for token in line.split():
                        if "=" in token:
                            key, _, value = token.partition("=")
                            if key == "JobName":
                                info.name = value
                            elif key == "JobState":
                                info.state = value
                            elif key == "Partition":
                                info.partition = value
                            elif key == "RunTime":
                                info.elapsed = value
                            elif key == "NodeList":
                                info.node = value
                            elif key == "SubmitTime":
                                info.submit_time = value
                            elif key == "StartTime":
                                info.start_time = value
                            elif key == "EndTime":
                                info.end_time = value
                            elif key == "ExitCode":
                                info.exit_code = value
                return info
        except Exception:
            pass
        return None

    # ── PBS ───────────────────────────────────────────────────────────────

    def _pbs_list(self, user: str) -> list[JobInfo]:
        """List PBS/Torque jobs."""
        jobs = []
        try:
            cmd = ["qstat"]
            if user:
                cmd.extend(["-u", user])

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                for line in result.stdout.strip().splitlines()[2:]:  # skip header
                    parts = line.split()
                    if parts:
                        jobs.append(JobInfo(
                            job_id=parts[0].split(".")[0],
                            name=parts[1] if len(parts) > 1 else "",
                            state=parts[4] if len(parts) > 4 else "",
                            elapsed=parts[3] if len(parts) > 3 else "",
                        ))
        except Exception:
            pass
        return jobs

    def _pbs_status(self, job_id: str) -> JobInfo | None:
        """Get PBS job details."""
        try:
            result = subprocess.run(
                ["qstat", "-f", job_id],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                info = JobInfo(job_id=job_id)
                for line in result.stdout.splitlines():
                    line = line.strip()
                    if line.startswith("Job_Name"):
                        info.name = line.split("=", 1)[1].strip()
                    elif line.startswith("job_state"):
                        info.state = line.split("=", 1)[1].strip()
                    elif line.startswith("queue"):
                        info.partition = line.split("=", 1)[1].strip()
                return info
        except Exception:
            pass
        return None
