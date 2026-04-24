"""Tests for Phase 4 (Domain Bioinformatics) and Phase 5 (Architecture) modules.

Covers:
    - DAG Topology Analyzer (circular dependency detection in Snakefiles)
    - Differential Privacy Scrubber (PHI/HIPAA redaction)
    - RLHF Data Store (feedback persistence)
    - Critic Agent (Multi-Agent Debate)
    - Time-Travel Debugger (snapshot/rewind)
"""

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from biopipe.core.dag_parser import DAGAnalyzer, DAGViolation
from biopipe.core.privacy import PrivacyScrubber
from biopipe.core.rlhf import RLHFDataStore
from biopipe.core.critic import CriticAgent, CriticResult
from biopipe.core.snapshots import TimeTravelDebugger
from biopipe.core.session import SessionManager
from biopipe.core.types import Message, Role


# ═══════════════════════════════════════════════════════════════════
# DAG Topology Analyzer
# ═══════════════════════════════════════════════════════════════════


class TestDAGAnalyzer:
    """Validate detection of circular dependencies in Snakefiles."""

    def test_clean_snakefile_passes(self):
        """A well-formed Snakefile with no cycles should return no violations."""
        snakefile = """
rule align:
    input: "reads.fastq"
    output: "aligned.bam"
    shell: "bwa mem ref.fa {input} > {output}"

rule sort:
    input: "aligned.bam"
    output: "sorted.bam"
    shell: "samtools sort {input} -o {output}"
"""
        violations = DAGAnalyzer.analyze_snakemake(snakefile)
        assert violations == []

    def test_circular_self_reference_detected(self):
        """A rule whose output is also its input is flagged."""
        snakefile = """
rule broken:
    input: "data.bam"
    output: "data.bam"
    shell: "samtools sort {input} -o {output}"
"""
        violations = DAGAnalyzer.analyze_snakemake(snakefile)
        assert len(violations) >= 1
        assert violations[0].type == "circular_dependency"
        assert "broken" in violations[0].description

    def test_empty_snakefile(self):
        """Empty content should produce no violations."""
        violations = DAGAnalyzer.analyze_snakemake("")
        assert violations == []

    def test_multiple_clean_rules(self):
        """Multiple non-circular rules should all pass."""
        snakefile = """
rule step1:
    input: "a.txt"
    output: "b.txt"

rule step2:
    input: "b.txt"
    output: "c.txt"

rule step3:
    input: "c.txt"
    output: "d.txt"
"""
        violations = DAGAnalyzer.analyze_snakemake(snakefile)
        assert violations == []


# ═══════════════════════════════════════════════════════════════════
# Privacy Scrubber (HIPAA/PHI Redaction)
# ═══════════════════════════════════════════════════════════════════


class TestPrivacyScrubber:
    """Validate PHI redaction patterns."""

    def setup_method(self):
        self.scrubber = PrivacyScrubber()

    def test_email_redacted(self):
        text = "Contact researcher at john.doe@stanford.edu for details."
        result = self.scrubber.redact(text)
        assert "john.doe@stanford.edu" not in result
        assert "[REDACTED_EMAIL]" in result

    def test_ssn_redacted(self):
        text = "Patient SSN: 123-45-6789 was enrolled."
        result = self.scrubber.redact(text)
        assert "123-45-6789" not in result
        assert "[REDACTED_SSN]" in result

    def test_patient_id_redacted(self):
        text = "Submitted sample for patient ID-12345."
        result = self.scrubber.redact(text)
        assert "ID-12345" not in result
        assert "[REDACTED_PATIENT_ID]" in result

    def test_clean_text_unchanged(self):
        text = "fastqc aligned.bam --outdir qc_results"
        result = self.scrubber.redact(text)
        assert result == text

    def test_multiple_patterns_redacted(self):
        text = "Email: a@b.com, SSN: 999-88-7777, patient PT-5678"
        result = self.scrubber.redact(text)
        assert "a@b.com" not in result
        assert "999-88-7777" not in result
        assert "PT-5678" not in result


# ═══════════════════════════════════════════════════════════════════
# RLHF Data Store
# ═══════════════════════════════════════════════════════════════════


class TestRLHFDataStore:
    """Validate RLHF feedback persistence."""

    def test_log_and_read_feedback(self, tmp_path):
        """Feedback is persisted as JSONL and can be read back."""
        db_path = tmp_path / "feedback.jsonl"
        store = RLHFDataStore(db_path=db_path)

        store.log_feedback(
            prompt="Generate RNA-seq pipeline",
            script="#!/bin/bash\nfastqc *.fastq.gz",
            rating=5,
            feedback_text="Perfect output, no issues."
        )

        assert db_path.exists()
        with open(db_path, "r") as f:
            line = f.readline()
            entry = json.loads(line)
            assert entry["prompt"] == "Generate RNA-seq pipeline"
            assert entry["reward"] == 5
            assert "timestamp" in entry

    def test_multiple_feedbacks_appended(self, tmp_path):
        """Multiple log_feedback calls append, not overwrite."""
        db_path = tmp_path / "feedback.jsonl"
        store = RLHFDataStore(db_path=db_path)

        store.log_feedback("p1", "s1", 3, "ok")
        store.log_feedback("p2", "s2", 1, "bad")

        with open(db_path, "r") as f:
            lines = f.readlines()
            assert len(lines) == 2


# ═══════════════════════════════════════════════════════════════════
# Critic Agent
# ═══════════════════════════════════════════════════════════════════


class MockCriticLLM:
    """Mock LLM that returns controllable critic responses."""

    def __init__(self, response_json: str):
        self._response = response_json

    @property
    def model_id(self) -> str:
        return "mock-critic"

    async def generate(self, messages, tools=None, **kwargs):
        return Message(role=Role.ASSISTANT, content=self._response)

    async def health_check(self) -> bool:
        return True


class TestCriticAgent:
    """Validate the Critic Agent's review logic."""

    def test_critic_approves_good_script(self):
        llm = MockCriticLLM('{"approved": true, "feedback": "Looks good"}')
        critic = CriticAgent(llm)
        result = asyncio.run(critic.review_script(
            "#!/bin/bash\nset -euo pipefail\nfastqc *.fastq.gz\nmultiqc .",
            "Run QC on my reads"
        ))
        assert result.approved is True

    def test_critic_rejects_bad_script(self):
        llm = MockCriticLLM('{"approved": false, "feedback": "Missing BAM sort before indexing"}')
        critic = CriticAgent(llm)
        result = asyncio.run(critic.review_script(
            "#!/bin/bash\nsamtools index aligned.bam",
            "Align and index WGS reads"
        ))
        assert result.approved is False
        assert "BAM sort" in result.feedback

    def test_critic_handles_malformed_json(self):
        """If the critic LLM emits garbage, auto-approve to avoid deadlock."""
        llm = MockCriticLLM("This is not JSON at all.")
        critic = CriticAgent(llm)
        result = asyncio.run(critic.review_script("echo hello", "test"))
        assert result.approved is True  # fail-open

    def test_critic_handles_missing_fields(self):
        """JSON without required fields triggers auto-approve."""
        llm = MockCriticLLM('{"some_other_field": true}')
        critic = CriticAgent(llm)
        result = asyncio.run(critic.review_script("echo hello", "test"))
        assert result.approved is True


# ═══════════════════════════════════════════════════════════════════
# Time-Travel Debugger
# ═══════════════════════════════════════════════════════════════════


class TestTimeTravelDebugger:
    """Validate snapshot/rewind mechanics."""

    def _make_session(self) -> SessionManager:
        return SessionManager("You are a bioinformatics agent.")

    def test_take_and_list_snapshots(self):
        session = self._make_session()
        debugger = TimeTravelDebugger(session)

        debugger.take_snapshot(0)
        debugger.take_snapshot(1)
        debugger.take_snapshot(2)

        assert debugger.list_snapshots() == [0, 1, 2]

    def test_can_rewind_existing_snapshot(self):
        session = self._make_session()
        debugger = TimeTravelDebugger(session)

        debugger.take_snapshot(0)
        assert debugger.can_rewind(0) is True
        assert debugger.can_rewind(99) is False

    def test_rewind_restores_state(self):
        session = self._make_session()
        debugger = TimeTravelDebugger(session)

        # Snapshot at iteration 0 (only system prompt)
        debugger.take_snapshot(0)

        # Add user message after snapshot
        session.add_user_message("Generate WGS pipeline")
        assert len(list(session.messages())) == 2  # system + user

        # Rewind to iteration 0 — user message should be gone
        debugger.rewind(0)
        msgs = list(session.messages())
        # After rewind, should only have the system prompt
        assert len(msgs) == 1
        assert msgs[0].role == Role.SYSTEM

    def test_rewind_deletes_future_snapshots(self):
        session = self._make_session()
        debugger = TimeTravelDebugger(session)

        debugger.take_snapshot(0)
        debugger.take_snapshot(1)
        debugger.take_snapshot(2)

        debugger.rewind(1)
        # Snapshot 2 should be gone (we altered the timeline)
        assert debugger.list_snapshots() == [0, 1]

    def test_rewind_nonexistent_raises(self):
        session = self._make_session()
        debugger = TimeTravelDebugger(session)

        with pytest.raises(ValueError, match="No snapshot found"):
            debugger.rewind(99)

    def test_max_snapshots_eviction(self):
        session = self._make_session()
        debugger = TimeTravelDebugger(session)
        debugger._max_snapshots = 5  # Lower for test

        for i in range(10):
            debugger.take_snapshot(i)

        # Only the last 5 should remain
        snaps = debugger.list_snapshots()
        assert len(snaps) == 5
        assert snaps[0] == 5  # oldest is 5, not 0
