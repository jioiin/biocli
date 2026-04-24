"""Deliberation engine: AI must justify every action before doing it.

Protocol:
1. AI receives task
2. AI checks available tools/plugins against task
3. AI proposes an action plan with justification
4. Plan is shown to user for approval
5. Only after approval → execution

The AI CANNOT self-modify, CANNOT discover new tools at runtime,
CANNOT execute without plan approval.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


class ApprovalStatus(Enum):
    """User approval state for a proposed action."""
    PENDING = auto()
    APPROVED = auto()
    REJECTED = auto()
    MODIFIED = auto()


@dataclass
class ProposedAction:
    """Single action the AI wants to take."""
    tool_name: str
    action_description: str
    justification: str          # WHY this tool for this task
    alternatives_considered: list[str]  # what else was available
    parameters: dict[str, Any] = field(default_factory=dict)
    risk_level: str = "low"     # "low" | "medium" | "high"
    approval: ApprovalStatus = ApprovalStatus.PENDING


@dataclass
class ActionPlan:
    """Complete plan the AI proposes before doing anything."""
    task_summary: str
    actions: list[ProposedAction]
    tools_available: list[str]
    tools_selected: list[str]
    tools_rejected: list[str]   # available but not chosen (with reasons)
    overall_justification: str
    estimated_output: str       # what the user should expect
    approval: ApprovalStatus = ApprovalStatus.PENDING

    def format_for_user(self) -> str:
        """Human-readable plan summary for terminal display."""
        lines = [
            f"Task: {self.task_summary}",
            "",
            f"Available tools: {', '.join(self.tools_available)}",
            f"Selected: {', '.join(self.tools_selected)}",
        ]

        if self.tools_rejected:
            lines.append(f"Not used: {', '.join(self.tools_rejected)}")

        lines.append("")
        lines.append("Proposed steps:")

        for i, action in enumerate(self.actions, 1):
            risk_icon = {"low": " ", "medium": "!", "high": "!!"}.get(
                action.risk_level, " "
            )
            lines.append(
                f"  {i}. [{risk_icon}] {action.tool_name}: {action.action_description}"
            )
            lines.append(f"     Why: {action.justification}")
            if action.alternatives_considered:
                lines.append(
                    f"     Alternatives: {', '.join(action.alternatives_considered)}"
                )

        lines.append("")
        lines.append(f"Expected output: {self.estimated_output}")
        return "\n".join(lines)


class DeliberationEngine:
    """Enforces the deliberation protocol.

    The AI MUST:
    1. Survey all available tools
    2. Match tools to task requirements
    3. Justify each selection
    4. Present plan for approval
    5. Execute ONLY after approval

    The AI CANNOT:
    - Skip deliberation
    - Self-approve
    - Discover tools not in registry
    - Modify its own capabilities
    """

    def __init__(self, available_tools: list[str]) -> None:
        self._available_tools = available_tools
        self._history: list[ActionPlan] = []

    def create_plan(
        self,
        task: str,
        selected_tools: list[str],
        actions: list[ProposedAction],
        justification: str,
        expected_output: str,
    ) -> ActionPlan:
        """Create an action plan that requires user approval."""
        # Validate: selected tools must be in available set
        unknown = set(selected_tools) - set(self._available_tools)
        if unknown:
            raise ValueError(
                f"AI selected tools not in registry: {unknown}. "
                f"Available: {self._available_tools}. "
                f"AI cannot discover or create tools at runtime."
            )

        rejected = [t for t in self._available_tools if t not in selected_tools]

        plan = ActionPlan(
            task_summary=task,
            actions=actions,
            tools_available=list(self._available_tools),
            tools_selected=selected_tools,
            tools_rejected=rejected,
            overall_justification=justification,
            estimated_output=expected_output,
        )

        self._history.append(plan)
        return plan

    def approve(self, plan: ActionPlan) -> ActionPlan:
        """User approves the plan."""
        plan.approval = ApprovalStatus.APPROVED
        for action in plan.actions:
            action.approval = ApprovalStatus.APPROVED
        return plan

    def reject(self, plan: ActionPlan, reason: str = "") -> ActionPlan:
        """User rejects the plan."""
        plan.approval = ApprovalStatus.REJECTED
        return plan

    def is_approved(self, plan: ActionPlan) -> bool:
        """Check if plan is approved for execution."""
        return plan.approval == ApprovalStatus.APPROVED

    def history(self) -> list[ActionPlan]:
        """Return all plans (for audit trail)."""
        return list(self._history)
