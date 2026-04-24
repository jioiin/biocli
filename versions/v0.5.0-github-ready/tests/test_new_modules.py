"""Tests for PipelineState, PluginSDK, Deliberation, Execution."""

import pytest

from biopipe.core.pipeline_state import PipelineState, PipelineStep
from biopipe.core.plugin_sdk import PluginLoader, PluginManifest, _FORBIDDEN_CAPABILITIES
from biopipe.core.deliberation import DeliberationEngine, ProposedAction, ApprovalStatus
from biopipe.core.execution import ExecutionEngine
from biopipe.core.safety import SafetyValidator
from biopipe.core.logger import StructuredLogger
from biopipe.core.config import DEFAULT_ALLOWLIST
from biopipe.core.errors import PermissionDeniedError, SafetyBlockedError
from biopipe.core.types import PermissionLevel


# === PipelineState Tests ===

class TestPipelineState:
    def test_empty_state(self) -> None:
        ps = PipelineState()
        assert ps.is_empty()
        assert "empty" in ps.format_for_llm().lower()

    def test_add_step(self) -> None:
        ps = PipelineState(reference_genome="hg38", sequencing_type="paired-end")
        ps.add_step(PipelineStep(order=1, tool="fastqc", action="QC", script_lines="fastqc sample.fq"))
        assert not ps.is_empty()
        assert "fastqc" in ps.current_script
        assert len(ps.steps) == 1

    def test_multi_step_accumulation(self) -> None:
        ps = PipelineState()
        ps.add_step(PipelineStep(order=1, tool="fastqc", action="QC", script_lines="fastqc s.fq"))
        ps.add_step(PipelineStep(order=2, tool="bwa", action="align", script_lines="bwa mem ref.fa s.fq"))
        assert "fastqc" in ps.current_script
        assert "bwa" in ps.current_script
        assert ps.current_script.index("fastqc") < ps.current_script.index("bwa")

    def test_format_preserves_metadata(self) -> None:
        ps = PipelineState(reference_genome="mm39", organism="mouse")
        formatted = ps.format_for_llm()
        assert "mm39" in formatted
        assert "mouse" in formatted

    def test_update_script_replaces(self) -> None:
        ps = PipelineState()
        ps.update_script("old script")
        ps.update_script("new script")
        assert ps.current_script == "new script"


# === PluginSDK Tests ===

class TestPluginSDK:
    def test_forbidden_capabilities(self) -> None:
        assert "execute" in _FORBIDDEN_CAPABILITIES
        assert "network" in _FORBIDDEN_CAPABILITIES
        assert "disable_safety" in _FORBIDDEN_CAPABILITIES

    def test_manifest_with_forbidden_perm_rejected(self) -> None:
        manifest = PluginManifest(
            name="evil", version="1.0", author="hacker",
            description="bad plugin", permissions=["execute"]
        )
        with pytest.raises(PermissionDeniedError, match="forbidden"):
            PluginLoader._validate_manifest(manifest)

    def test_manifest_with_safe_perm_ok(self) -> None:
        manifest = PluginManifest(
            name="good", version="1.0", author="dev",
            description="safe plugin", permissions=["read_docs"]
        )
        PluginLoader._validate_manifest(manifest)  # should not raise

    def test_discover_empty_dir(self) -> None:
        loader = PluginLoader(plugin_dir="/nonexistent/path")
        assert loader.discover() == []

    def test_list_loaded_empty(self) -> None:
        loader = PluginLoader()
        assert loader.list_loaded() == []


# === Deliberation Tests ===

class TestDeliberation:
    def test_create_plan_with_valid_tools(self) -> None:
        engine = DeliberationEngine(["fastqc", "bwa", "gatk"])
        action = ProposedAction(
            tool_name="fastqc", action_description="Quality control",
            justification="Standard first step for NGS QC",
            alternatives_considered=["qualimap"]
        )
        plan = engine.create_plan(
            task="QC pipeline", selected_tools=["fastqc"],
            actions=[action], justification="QC needed",
            expected_output="fastqc_report.html"
        )
        assert plan.approval == ApprovalStatus.PENDING
        assert len(plan.tools_rejected) == 2  # bwa, gatk not selected

    def test_cannot_select_unknown_tools(self) -> None:
        engine = DeliberationEngine(["fastqc", "bwa"])
        action = ProposedAction(
            tool_name="nonexistent", action_description="hack",
            justification="none", alternatives_considered=[]
        )
        with pytest.raises(ValueError, match="not in registry"):
            engine.create_plan(
                task="bad", selected_tools=["nonexistent"],
                actions=[action], justification="",
                expected_output=""
            )

    def test_approve_reject_flow(self) -> None:
        engine = DeliberationEngine(["fastqc"])
        action = ProposedAction(
            tool_name="fastqc", action_description="QC",
            justification="needed", alternatives_considered=[]
        )
        plan = engine.create_plan(
            task="QC", selected_tools=["fastqc"],
            actions=[action], justification="QC",
            expected_output="report"
        )
        assert not engine.is_approved(plan)
        engine.approve(plan)
        assert engine.is_approved(plan)

    def test_reject_prevents_approval(self) -> None:
        engine = DeliberationEngine(["fastqc"])
        action = ProposedAction(
            tool_name="fastqc", action_description="QC",
            justification="needed", alternatives_considered=[]
        )
        plan = engine.create_plan(
            task="QC", selected_tools=["fastqc"],
            actions=[action], justification="QC",
            expected_output="report"
        )
        engine.reject(plan, "not needed")
        assert not engine.is_approved(plan)

    def test_history_tracked(self) -> None:
        engine = DeliberationEngine(["fastqc"])
        action = ProposedAction(
            tool_name="fastqc", action_description="QC",
            justification="needed", alternatives_considered=[]
        )
        engine.create_plan(
            task="QC1", selected_tools=["fastqc"],
            actions=[action], justification="1",
            expected_output="r1"
        )
        engine.create_plan(
            task="QC2", selected_tools=["fastqc"],
            actions=[action], justification="2",
            expected_output="r2"
        )
        assert len(engine.history()) == 2

    def test_format_for_user(self) -> None:
        engine = DeliberationEngine(["fastqc", "bwa"])
        action = ProposedAction(
            tool_name="fastqc", action_description="Quality control",
            justification="Standard QC step",
            alternatives_considered=["qualimap"],
            risk_level="low"
        )
        plan = engine.create_plan(
            task="NGS QC", selected_tools=["fastqc"],
            actions=[action], justification="QC is mandatory",
            expected_output="QC report"
        )
        text = plan.format_for_user()
        assert "fastqc" in text
        assert "bwa" in text  # in rejected
        assert "qualimap" in text  # in alternatives


# === Execution Engine Tests ===

class TestExecution:
    def _make_engine(self, level: PermissionLevel = PermissionLevel.GENERATE) -> ExecutionEngine:
        return ExecutionEngine(
            permission_level=level,
            safety=SafetyValidator(allowlist=DEFAULT_ALLOWLIST),
            logger=StructuredLogger(),
        )

    def test_cannot_execute_at_generate_level(self) -> None:
        engine = self._make_engine(PermissionLevel.GENERATE)
        assert not engine.can_execute()

    def test_can_execute_at_execute_level(self) -> None:
        engine = self._make_engine(PermissionLevel.EXECUTE)
        assert engine.can_execute()

    def test_save_script_always_works(self, tmp_path) -> None:
        engine = ExecutionEngine(
            permission_level=PermissionLevel.GENERATE,
            safety=SafetyValidator(allowlist=DEFAULT_ALLOWLIST),
            logger=StructuredLogger(),
            workspace=tmp_path,
        )
        path = engine.save_script("#!/bin/bash\necho hello", "test.sh")
        assert path.exists()
        assert path.read_text() == "#!/bin/bash\necho hello"

    def test_execute_blocked_without_permission(self) -> None:
        engine = self._make_engine(PermissionLevel.GENERATE)
        from biopipe.core.deliberation import ActionPlan, ProposedAction
        plan = ActionPlan(
            task_summary="test", actions=[], tools_available=[],
            tools_selected=[], tools_rejected=[],
            overall_justification="test", estimated_output="test",
            approval=ApprovalStatus.APPROVED,
        )
        with pytest.raises(PermissionDeniedError, match="EXECUTE"):
            engine.execute("echo hi", plan=plan, user_confirmed=True)

    def test_execute_blocked_without_approval(self) -> None:
        engine = self._make_engine(PermissionLevel.EXECUTE)
        from biopipe.core.deliberation import ActionPlan
        plan = ActionPlan(
            task_summary="test", actions=[], tools_available=[],
            tools_selected=[], tools_rejected=[],
            overall_justification="test", estimated_output="test",
            approval=ApprovalStatus.PENDING,  # NOT approved
        )
        with pytest.raises(PermissionDeniedError, match="not approved"):
            engine.execute("echo hi", plan=plan, user_confirmed=True)

    def test_execute_blocked_without_user_confirm(self) -> None:
        engine = self._make_engine(PermissionLevel.EXECUTE)
        from biopipe.core.deliberation import ActionPlan
        plan = ActionPlan(
            task_summary="test", actions=[], tools_available=[],
            tools_selected=[], tools_rejected=[],
            overall_justification="test", estimated_output="test",
            approval=ApprovalStatus.APPROVED,
        )
        with pytest.raises(PermissionDeniedError, match="confirm"):
            engine.execute("echo hi", plan=plan, user_confirmed=False)

    def test_execute_blocked_by_safety(self) -> None:
        engine = self._make_engine(PermissionLevel.EXECUTE)
        from biopipe.core.deliberation import ActionPlan
        plan = ActionPlan(
            task_summary="test", actions=[], tools_available=[],
            tools_selected=[], tools_rejected=[],
            overall_justification="test", estimated_output="test",
            approval=ApprovalStatus.APPROVED,
        )
        with pytest.raises(SafetyBlockedError):
            engine.execute("rm -rf /", plan=plan, user_confirmed=True)
