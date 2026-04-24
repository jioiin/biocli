"""Tests for agent modules: workspace, shell, profiler, git, memory, tool selection, decomposer."""

import json
import pytest
import sys
import shutil
from pathlib import Path

from biopipe.core.workspace import WorkspaceScanner
from biopipe.core.shell_tool import ShellTool
from biopipe.core.system_profiler import SystemProfiler
from biopipe.core.git_tool import GitTool
from biopipe.core.memory import ContextMemory
from biopipe.core.tool_selection import ToolSelector
from biopipe.core.task_decomposer import TaskDecomposer


class TestWorkspaceScanner:
    def test_scan_current_dir(self) -> None:
        scanner = WorkspaceScanner()
        summary = scanner.scan(".")
        assert summary.root
        assert isinstance(summary.files, list)

    def test_scan_with_files(self, tmp_path: Path) -> None:
        (tmp_path / "sample.fastq.gz").write_text("@SEQ")
        (tmp_path / "ref.fa").write_text(">chr1")
        (tmp_path / "pipeline.sh").write_text("#!/bin/bash")
        scanner = WorkspaceScanner()
        summary = scanner.scan(tmp_path)
        assert summary.has_files("fastq")
        assert summary.has_files("reference")
        assert summary.has_files("script")

    def test_format_for_llm(self, tmp_path: Path) -> None:
        (tmp_path / "data.bam").write_text("bam")
        scanner = WorkspaceScanner()
        summary = scanner.scan(tmp_path)
        fmt = summary.format_for_llm()
        assert "<workspace>" in fmt
        assert "bam" in fmt


class TestShellTool:
    @pytest.mark.skipif(sys.platform == "win32", reason="Requires UNIX 'uname' command")
    def test_whitelisted_command(self) -> None:
        shell = ShellTool()
        result = shell.run("uname -s")
        assert result.allowed
        assert result.exit_code == 0

    def test_blocked_command(self) -> None:
        shell = ShellTool()
        result = shell.run("rm -rf /")
        assert not result.allowed

    def test_blocked_flag(self) -> None:
        shell = ShellTool()
        result = shell.run("find . --delete")
        assert not result.allowed

    def test_git_push_blocked(self) -> None:
        shell = ShellTool()
        result = shell.run("git push origin main")
        assert not result.allowed

    def test_git_status_allowed(self) -> None:
        shell = ShellTool()
        result = shell.run("git status")
        # May fail if not in a git repo, but should be allowed
        assert result.allowed

    def test_nonexistent_command(self) -> None:
        shell = ShellTool()
        result = shell.run("totally_fake_command_xyz")
        assert not result.allowed


class TestSystemProfiler:
    def test_profile_runs(self) -> None:
        profiler = SystemProfiler()
        profile = profiler.profile()
        assert profile.cpu_count >= 1
        assert profile.os_name != ""

    def test_format_for_llm(self) -> None:
        profiler = SystemProfiler()
        profile = profiler.profile()
        fmt = profile.format_for_llm()
        assert "<system_profile>" in fmt
        assert "CPU" in fmt

    def test_recommended_threads(self) -> None:
        profiler = SystemProfiler()
        profile = profiler.profile()
        threads = profile.recommended_threads()
        assert 1 <= threads <= profile.cpu_count


@pytest.mark.skipif(not shutil.which("git"), reason="Git not installed")
class TestGitTool:
    def test_init_and_status(self, tmp_path: Path) -> None:
        git = GitTool(workspace=tmp_path)
        result = git.init()
        assert result.success
        status = git.status()
        assert status.success

    def test_add_and_commit(self, tmp_path: Path) -> None:
        git = GitTool(workspace=tmp_path)
        git.init()
        (tmp_path / "test.sh").write_text("#!/bin/bash\necho hello")
        git.add("test.sh")
        # Need to set git user for commit
        import subprocess
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path))
        subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path))
        result = git.commit("test commit")
        assert result.success

    def test_push_blocked(self, tmp_path: Path) -> None:
        git = GitTool(workspace=tmp_path)
        result = git._run("git push origin main")
        assert not result.success
        assert "blocked" in result.stderr.lower()

    def test_pull_blocked(self, tmp_path: Path) -> None:
        git = GitTool(workspace=tmp_path)
        result = git._run("git pull")
        assert not result.success

    def test_log(self, tmp_path: Path) -> None:
        git = GitTool(workspace=tmp_path)
        git.init()
        result = git.log()
        # Empty repo has no commits, but command should work
        assert isinstance(result.stdout, str)


class TestContextMemory:
    def test_remember_and_recall(self, tmp_path: Path) -> None:
        mem = ContextMemory(path=str(tmp_path / "mem.json"))
        mem.remember("genome", "hg38", category="genome")
        assert mem.recall("genome") == "hg38"

    def test_persistence(self, tmp_path: Path) -> None:
        path = str(tmp_path / "mem.json")
        mem1 = ContextMemory(path=path)
        mem1.remember("organism", "mouse", category="project")

        mem2 = ContextMemory(path=path)
        assert mem2.recall("organism") == "mouse"

    def test_forget(self, tmp_path: Path) -> None:
        mem = ContextMemory(path=str(tmp_path / "mem.json"))
        mem.remember("temp", "value")
        assert mem.forget("temp")
        assert mem.recall("temp") is None

    def test_category_recall(self, tmp_path: Path) -> None:
        mem = ContextMemory(path=str(tmp_path / "mem.json"))
        mem.remember("g1", "hg38", category="genome")
        mem.remember("g2", "mm39", category="genome")
        mem.remember("t1", "bwa", category="tool_preference")
        genomes = mem.recall_category("genome")
        assert len(genomes) == 2

    def test_format_for_llm(self, tmp_path: Path) -> None:
        mem = ContextMemory(path=str(tmp_path / "mem.json"))
        mem.remember("genome", "hg38", category="genome")
        fmt = mem.format_for_llm()
        assert "<memory>" in fmt
        assert "hg38" in fmt


class TestToolSelector:
    def test_rnaseq_alignment(self) -> None:
        sel = ToolSelector()
        rec = sel.recommend("rnaseq", "align")
        assert rec is not None
        assert rec.tool == "hisat2"
        assert "BWA" in rec.warnings[0]

    def test_wgs_alignment(self) -> None:
        sel = ToolSelector()
        rec = sel.recommend("wgs", "align")
        assert rec is not None
        assert rec.tool == "bwa"

    def test_validate_wrong_choice(self) -> None:
        sel = ToolSelector()
        warnings = sel.validate_choice("rnaseq", "align", "bwa")
        assert len(warnings) > 0
        assert any("BWA" in w or "bwa" in w for w in warnings)

    def test_validate_correct_choice(self) -> None:
        sel = ToolSelector()
        warnings = sel.validate_choice("rnaseq", "align", "hisat2")
        assert len(warnings) == 0

    def test_validate_alternative(self) -> None:
        sel = ToolSelector()
        warnings = sel.validate_choice("rnaseq", "align", "star")
        assert len(warnings) > 0  # valid but not default

    def test_available_pipelines(self) -> None:
        sel = ToolSelector()
        types = sel.available_pipelines()
        assert "rnaseq" in types
        assert "wgs" in types
        assert "atacseq" in types

    def test_format_for_llm(self) -> None:
        sel = ToolSelector()
        fmt = sel.format_for_llm("rnaseq")
        assert "hisat2" in fmt
        assert "tool_rules" in fmt


class TestTaskDecomposer:
    def test_rnaseq_decomposition(self) -> None:
        dec = TaskDecomposer()
        plan = dec.decompose("RNA-seq analysis", "rnaseq")
        assert len(plan.subtasks) == 6
        assert plan.subtasks[0].tool == "fastqc"
        assert plan.subtasks[2].tool == "hisat2"

    def test_wgs_decomposition(self) -> None:
        dec = TaskDecomposer()
        plan = dec.decompose("WGS variant calling", "wgs")
        assert len(plan.subtasks) == 7
        assert plan.subtasks[2].tool == "bwa"
        assert plan.subtasks[5].tool == "gatk"

    def test_unknown_type_fallback(self) -> None:
        dec = TaskDecomposer()
        plan = dec.decompose("custom analysis", "unknown_type")
        assert len(plan.subtasks) == 1

    def test_step_ordering(self) -> None:
        dec = TaskDecomposer()
        plan = dec.decompose("test", "rnaseq")
        for i, st in enumerate(plan.subtasks):
            assert st.order == i + 1

    def test_format_for_user(self) -> None:
        dec = TaskDecomposer()
        plan = dec.decompose("RNA-seq", "rnaseq")
        text = plan.format_for_user()
        assert "fastqc" in text
        assert "hisat2" in text

    def test_next_pending(self) -> None:
        dec = TaskDecomposer()
        plan = dec.decompose("test", "rnaseq")
        first = plan.next_pending()
        assert first is not None
        assert first.order == 1
        plan.mark_validated(1)
        second = plan.next_pending()
        assert second is not None
        assert second.order == 2

    def test_is_complete(self) -> None:
        dec = TaskDecomposer()
        plan = dec.decompose("test", "atacseq")
        assert not plan.is_complete()
        for st in plan.subtasks:
            plan.mark_validated(st.order)
        assert plan.is_complete()
