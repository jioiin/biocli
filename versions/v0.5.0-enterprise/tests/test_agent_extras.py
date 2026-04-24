"""Tests for project context, audit trail, and error recovery."""

import json
import pytest
from pathlib import Path

from biopipe.core.project_context import BiopipeMDReader, ProjectContext
from biopipe.core.audit import AuditTrail
from biopipe.core.error_recovery import ErrorRecovery


# === BIOPIPE.md Reader Tests ===

class TestProjectContext:
    def test_parse_full_file(self, tmp_path: Path) -> None:
        md = tmp_path / "BIOPIPE.md"
        md.write_text("""# Test Project
organism: Mus musculus
genome: mm39
sequencing: paired-end Illumina
cluster: Sherlock
partition: normal
adapters: TruSeq
conventions:
  - Use fastp
  - STAR preferred
  - Comment every flag
""")
        reader = BiopipeMDReader()
        ctx = reader.read(str(tmp_path))
        assert ctx.organism == "Mus musculus"
        assert ctx.genome == "mm39"
        assert ctx.sequencing == "paired-end Illumina"
        assert ctx.cluster == "Sherlock"
        assert ctx.adapters == "TruSeq"
        assert len(ctx.conventions) == 3
        assert "fastp" in ctx.conventions[0]

    def test_missing_file_returns_empty(self) -> None:
        reader = BiopipeMDReader()
        ctx = reader.read("/nonexistent/path")
        assert ctx.is_empty()

    def test_format_for_llm(self, tmp_path: Path) -> None:
        md = tmp_path / "BIOPIPE.md"
        md.write_text("organism: Human\ngenome: hg38\n")
        reader = BiopipeMDReader()
        ctx = reader.read(str(tmp_path))
        formatted = ctx.format_for_llm()
        assert "Human" in formatted
        assert "hg38" in formatted
        assert "<project_context>" in formatted

    def test_walk_up_directories(self, tmp_path: Path) -> None:
        # BIOPIPE.md in parent, reader called from child
        md = tmp_path / "BIOPIPE.md"
        md.write_text("organism: Zebrafish\n")
        child = tmp_path / "subdir"
        child.mkdir()
        reader = BiopipeMDReader()
        ctx = reader.read(str(child))
        assert ctx.organism == "Zebrafish"

    def test_extra_keys_captured(self, tmp_path: Path) -> None:
        md = tmp_path / "BIOPIPE.md"
        md.write_text("organism: Fly\ncustom_key: custom_value\n")
        reader = BiopipeMDReader()
        ctx = reader.read(str(tmp_path))
        assert ctx.extra["custom_key"] == "custom_value"


# === Audit Trail Tests ===

class TestAuditTrail:
    def test_record_and_count(self) -> None:
        trail = AuditTrail(session_id="test123", model_id="llama3")
        trail.record(
            event_type="generation",
            prompt="make QC",
            output="#!/bin/bash\nfastqc s.fq",
            safety_passed=True,
            violations=[],
            approval="approved",
            script_hash="abc123",
        )
        assert trail.count() == 1

    def test_export_json(self, tmp_path: Path) -> None:
        trail = AuditTrail(session_id="s1", model_id="llama3")
        trail.record(
            event_type="generation", prompt="test",
            output="echo hi", safety_passed=True,
            violations=[], approval="approved", script_hash="xyz",
        )
        path = trail.export_json(tmp_path / "audit.json")
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["session_id"] == "s1"
        assert data["total_records"] == 1
        assert data["all_passed_safety"] is True

    def test_export_markdown(self, tmp_path: Path) -> None:
        trail = AuditTrail(session_id="s2", model_id="llama3")
        trail.record(
            event_type="generation", prompt="test",
            output="echo hi", safety_passed=False,
            violations=[{"severity": "critical", "description": "rm -rf detected"}],
            approval="blocked", script_hash="xyz",
        )
        path = trail.export_markdown(tmp_path / "audit.md")
        assert path.exists()
        content = path.read_text()
        assert "BLOCKED" in content
        assert "rm -rf" in content

    def test_json_safety_aggregate(self, tmp_path: Path) -> None:
        trail = AuditTrail(session_id="s3", model_id="llama3")
        trail.record(
            event_type="g1", prompt="p1", output="o1",
            safety_passed=True, violations=[], approval="ok", script_hash="a",
        )
        trail.record(
            event_type="g2", prompt="p2", output="o2",
            safety_passed=False, violations=[{"severity": "critical", "description": "bad"}],
            approval="blocked", script_hash="b",
        )
        path = trail.export_json(tmp_path / "audit.json")
        data = json.loads(path.read_text())
        assert data["all_passed_safety"] is False


# === Error Recovery Tests ===

class TestErrorRecovery:
    def setup_method(self) -> None:
        self.recovery = ErrorRecovery()

    def test_bwa_missing_index(self) -> None:
        stderr = "[bwa_index] fail to open file 'reference.fa.bwt'"
        diagnoses = self.recovery.diagnose(stderr)
        assert len(diagnoses) == 1
        assert diagnoses[0].tool == "bwa"
        assert "index" in diagnoses[0].suggestion.lower()

    def test_gatk_missing_read_group(self) -> None:
        stderr = "Read group SAMPLE1 not found in BAM header"
        diagnoses = self.recovery.diagnose(stderr)
        assert len(diagnoses) == 1
        assert diagnoses[0].tool == "gatk"
        assert "@RG" in diagnoses[0].suggestion

    def test_command_not_found(self) -> None:
        stderr = "bash: bwa: command not found"
        diagnoses = self.recovery.diagnose(stderr)
        assert len(diagnoses) == 1
        assert diagnoses[0].error_type == "tool_missing"

    def test_out_of_memory(self) -> None:
        stderr = "Killed\n[some process] Out of memory"
        diagnoses = self.recovery.diagnose(stderr)
        assert any(d.error_type == "oom" for d in diagnoses)

    def test_disk_full(self) -> None:
        stderr = "samtools sort: No space left on device"
        diagnoses = self.recovery.diagnose(stderr)
        assert any(d.error_type == "disk_full" for d in diagnoses)

    def test_slurm_bad_partition(self) -> None:
        stderr = "SBATCH: error: Batch job submission Partition gpu not available"
        diagnoses = self.recovery.diagnose(stderr)
        assert any(d.tool == "slurm" for d in diagnoses)

    def test_clean_stderr_no_diagnoses(self) -> None:
        stderr = "Processing sample_01.fastq.gz...\nDone."
        diagnoses = self.recovery.diagnose(stderr)
        assert len(diagnoses) == 0

    def test_multiple_errors(self) -> None:
        stderr = (
            "bash: bwa: command not found\n"
            "No space left on device\n"
            "Permission denied\n"
        )
        diagnoses = self.recovery.diagnose(stderr)
        assert len(diagnoses) == 3

    def test_format_report(self) -> None:
        stderr = "[bwa_index] fail to open file 'ref.fa.bwt'"
        diagnoses = self.recovery.diagnose(stderr)
        report = self.recovery.format_report(diagnoses)
        assert "bwa" in report
        assert "Fix:" in report

    def test_deduplication(self) -> None:
        stderr = (
            "bash: bwa: command not found\n"
            "bash: bwa: command not found\n"
            "bash: bwa: command not found\n"
        )
        diagnoses = self.recovery.diagnose(stderr)
        assert len(diagnoses) == 1  # deduplicated
