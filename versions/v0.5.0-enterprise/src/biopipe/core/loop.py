"""Agent loop: the heart of BioPipe-CLI.

Cycle: user input → RAG retrieval → LLM → tool calls → safety → output.
Pattern from Claude Code Rust rewrite, extended with RAG injection.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from .errors import SafetyBlockedError
from .hooks import HookRegistry
from .logger import StructuredLogger
from .router import Router
from .safety import SafetyValidator
from .session import SessionManager
from .snapshots import TimeTravelDebugger
from .critic import CriticAgent
from .tool_scheduler import ToolScheduler
from .types import HookPoint, LLMProvider, Message, Role, SafetyReport

if TYPE_CHECKING:
    from biopipe.rag.retriever import RAGRetriever


class AgentLoop:
    """Stateless loop. All state lives in SessionManager."""

    def __init__(
        self,
        llm: LLMProvider,
        session: SessionManager,
        router: Router,
        scheduler: ToolScheduler,
        safety: SafetyValidator,
        hooks: HookRegistry,
        logger: StructuredLogger,
        max_iterations: int = 10,
        rag: RAGRetriever | None = None,
        rag_top_k: int = 5,
        rag_template: str = "{chunks}",
    ) -> None:
        self._llm = llm
        self._session = session
        self._router = router
        self._scheduler = scheduler
        self._safety = safety
        self._hooks = hooks
        self._logger = logger
        self._max_iterations = max_iterations
        self._rag = rag
        self._rag_top_k = rag_top_k
        self._rag_template = rag_template
        self._debugger = TimeTravelDebugger(session)
        self._critic = CriticAgent(llm)

    async def run(self, user_input: str, stream_callback: Callable[[str], None] | None = None) -> str:
        """Run the full agent loop. Returns final text output."""
        sandboxed = self._session.add_user_message(user_input)
        self._logger.log("user_input", {
            "length": len(user_input),
            "injection_score": sandboxed.injection_score,
        })

        # RAG: retrieve relevant documentation and inject into context
        self._inject_rag_context(user_input)

        for iteration in range(self._max_iterations):
            # Save state for potential Time-Travel rewind by the Critic
            self._debugger.take_snapshot(iteration)

            ctx = await self._hooks.fire(
                HookPoint.BEFORE_LLM_CALL,
                {"messages": self._session.messages(), "iteration": iteration},
            )

            tools = self._router._registry.list_schemas()
            response = await self._llm.generate(ctx["messages"], tools, stream_callback=stream_callback)
            self._logger.log("llm_response", {"has_tool_calls": bool(response.tool_calls)})

            await self._hooks.fire(HookPoint.AFTER_LLM_CALL, {"response": response})

            if not response.tool_calls:
                report = self._validate_output(response.content)
                if not report.passed:
                    raise SafetyBlockedError(
                        f"Output blocked: {[v.description for v in report.violations if v.severity == 'critical']}"
                    )

                # ── MULTI-AGENT DEBATE ──────────────────────────────────────
                # Critic Agent reviews the final output before we return
                critic_result = await self._critic.review_script(response.content, user_input)
                if not critic_result.approved:
                    self._logger.log("critic_rejected", {"feedback": critic_result.feedback})
                    # Time-Travel Rewind! We cancel this iteration's hallucination.
                    self._debugger.rewind(iteration)
                    # Inject Critic's feedback via system message
                    self._session.add(Message(
                        role=Role.SYSTEM,
                        content=f"CRITIC AGENT REJECTED YOUR SCRIPT: {critic_result.feedback}\nFix it immediately."
                    ))
                    continue # Retry this iteration step
                
                # If approved, proceed normally
                self._logger.log("critic_approved", {})
                self._session.add(response)
                return response.content

            results = await self._scheduler.schedule(response.tool_calls)

            for result in results:
                if result.artifacts:
                    for artifact in result.artifacts:
                        report = self._validate_output(result.output)
                        if not report.passed:
                            raise SafetyBlockedError(
                                f"Artifact blocked: {[v.description for v in report.violations if v.severity == 'critical']}"
                            )

                self._session.add(Message(
                    role=Role.TOOL,
                    content=result.output,
                    tool_result=result,
                ))

            self._session.compact()

        return "Maximum iterations reached. Please refine your request."

    def _inject_rag_context(self, query: str) -> None:
        """Retrieve relevant docs from RAG and inject as system message."""
        if self._rag is None:
            return
        try:
            if self._rag.is_empty():
                return
            chunks = self._rag.search(query, top_k=self._rag_top_k)
            if not chunks:
                return
            context = self._rag.format_context(chunks)
            rag_msg = self._rag_template.format(chunks=context)
            self._session.add(Message(role=Role.SYSTEM, content=rag_msg))
            self._logger.log("rag_retrieval", {
                "chunks": len(chunks),
                "top_score": chunks[0].score if chunks else 0,
                "tools": list({c.tool_name for c in chunks}),
            })
        except Exception as exc:
            self._logger.log("rag_error", {"error": str(exc)})

    def _validate_output(self, content: str) -> SafetyReport:
        """Detect language and validate through safety."""
        language = "python" if "import " in content and "def " in content else "bash"
        report = self._safety.validate(content, language)
        self._logger.log("safety_check", {
            "passed": report.passed,
            "violations": len(report.violations),
            "critical": sum(1 for v in report.violations if v.severity == "critical"),
        })
        return report
