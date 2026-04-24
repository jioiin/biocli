"""Supervised execution engine.

Manages the transition from GENERATE (dry-run) to EXECUTE (real run).
Every execution requires:
1. Approved ActionPlan from DeliberationEngine
2. Safety validation passed
3. User confirmation at execution time
4. Full audit logging
"""

from __future__ import annotations

import subprocess
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .deliberation import ActionPlan, ApprovalStatus
from .errors import PermissionDeniedError, SafetyBlockedError
from .logger import StructuredLogger
from .safety import SafetyValidator
from .types import PermissionLevel, SafetyReport


@dataclass
class ExecutionResult:
    """Result of a supervised execution."""
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    script_path: str
    safety_report: SafetyReport


class ExecutionEngine:
    """Execute scripts ONLY under strict supervision.

    Requires:
    - PermissionLevel.EXECUTE (not available in MVP)
    - Approved ActionPlan
    - Safety validation passed (no CRITICAL)
    - User confirmation (interactive prompt)
    """

    def __init__(
        self,
        permission_level: PermissionLevel,
        safety: SafetyValidator,
        logger: StructuredLogger,
        workspace: Path | None = None,
    ) -> None:
        self._permission = permission_level
        self._safety = safety
        self._logger = logger
        self._workspace = workspace or Path("./biopipe_output")

    def can_execute(self) -> bool:
        """Check if execution is enabled."""
        return self._permission.value >= PermissionLevel.EXECUTE.value

    def save_script(self, script: str, filename: str) -> Path:
        """Save script to workspace (always allowed at GENERATE level)."""
        self._workspace.mkdir(parents=True, exist_ok=True)
        path = self._workspace / filename
        path.write_text(script, encoding="utf-8")
        self._logger.log("script_saved", {"path": str(path), "size": len(script)})
        return path

    def execute(
        self,
        script: str,
        plan: ActionPlan,
        user_confirmed: bool = False,
    ) -> ExecutionResult:
        """Execute a script under full supervision.

        This method will refuse to run if ANY condition is not met.

        Args:
            script: The bash script to execute.
            plan: Approved action plan from deliberation.
            user_confirmed: User explicitly said yes to execution.

        Returns:
            ExecutionResult with stdout, stderr, exit code.

        Raises:
            PermissionDeniedError: If permission level < EXECUTE.
            SafetyBlockedError: If safety validation fails.
        """
        # Gate 1: Permission level
        if not self.can_execute():
            raise PermissionDeniedError(
                "Execution requires PermissionLevel.EXECUTE. "
                "Current level: GENERATE (dry-run only). "
                "Set BIOPIPE_PERMISSION_LEVEL=EXECUTE to enable."
            )

        # Gate 2: Plan must be approved
        if plan.approval != ApprovalStatus.APPROVED:
            raise PermissionDeniedError(
                f"ActionPlan not approved. Status: {plan.approval.name}. "
                f"AI cannot self-approve execution."
            )

        # Gate 3: Safety validation
        report = self._safety.validate(script, language="bash")
        if not report.passed:
            critical = [v for v in report.violations if v.severity == "critical"]
            raise SafetyBlockedError(
                f"Script blocked by safety: {[v.description for v in critical]}"
            )

        # Gate 4: User confirmation
        if not user_confirmed:
            raise PermissionDeniedError(
                "User must explicitly confirm execution. "
                "Pass user_confirmed=True only after interactive approval."
            )

        # All gates passed — execute
        script_path = self.save_script(script, "execute_temp.sh")

        self._logger.log("execution_start", {
            "script_hash": report.script_hash,
            "plan_task": plan.task_summary,
            "tools": plan.tools_selected,
        })

        try:
            result = subprocess.run(
                ["bash", str(script_path)],
                capture_output=True,
                text=True,
                timeout=3600,  # 1 hour max
                cwd=str(self._workspace),
            )

            exec_result = ExecutionResult(
                success=result.returncode == 0,
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                script_path=str(script_path),
                safety_report=report,
            )

            self._logger.log("execution_end", {
                "success": exec_result.success,
                "exit_code": exec_result.exit_code,
                "stdout_len": len(exec_result.stdout),
                "stderr_len": len(exec_result.stderr),
            })

            return exec_result

        except subprocess.TimeoutExpired:
            self._logger.log("execution_timeout", {"timeout": 3600})
            return ExecutionResult(
                success=False,
                stdout="",
                stderr="Execution timed out after 1 hour",
                exit_code=-1,
                script_path=str(script_path),
                safety_report=report,
            )
