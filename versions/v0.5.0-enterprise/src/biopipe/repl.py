"""Interactive REPL: BioPipe-CLI as a terminal AI assistant.

Maintains session across turns, accumulates pipeline state,
supports slash commands, and shows deliberation plans.
"""

from __future__ import annotations

import asyncio
import sys

from biopipe.core.config import Config
from biopipe.core.deliberation import DeliberationEngine
from biopipe.core.errors import BioPipeError, SafetyBlockedError
from biopipe.core.execution import ExecutionEngine
from biopipe.core.pipeline_state import PipelineState
from biopipe.core.runtime import AgentRuntime


_BANNER = """
BioPipe-CLI v0.1.0 | {model} | RAG: {rag_status}
Plugins: {plugins}

Commands:
  /help        — show commands
  /plan        — show current pipeline plan
  /script      — show accumulated script
  /save [file] — save script to file
  /execute     — execute script (requires EXECUTE permission)
  /reset       — reset pipeline state
  /plugins     — list loaded plugins
  /explain     — explain a tool flag (e.g., /explain bwa -t)
  /quit        — exit

Type your request in natural language.
"""

_HELP = """
Ask me to build a pipeline step by step:

  > сделай QC для paired-end FASTQ
  > добавь выравнивание на hg38 через BWA
  > добавь variant calling через GATK
  > оберни в SLURM для 4 нод
  > сохрани скрипт

Or ask questions:
  > что делает флаг --dta в HISAT2?
  > какой алайнер лучше для RNA-seq?
"""


class BioPipeREPL:
    """Interactive REPL for BioPipe-CLI."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._pipeline = PipelineState()
        self._runtime: AgentRuntime | None = None
        self._execution: ExecutionEngine | None = None
        self._deliberation: DeliberationEngine | None = None

    def start(self) -> None:
        """Start the interactive REPL."""
        self._init_runtime()
        self._print_banner()

        while True:
            try:
                user_input = input("\n> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nExiting BioPipe-CLI.")
                asyncio.run(self._runtime.shutdown())
                break

            if not user_input:
                continue

            if user_input.startswith("/"):
                self._handle_command(user_input)
            else:
                self._handle_prompt(user_input)

    def _init_runtime(self) -> None:
        """Initialize runtime with LLM, tools, and plugins."""
        from biopipe.llm.ollama import OllamaLLM

        llm = OllamaLLM(
            base_url=self._config.ollama_url,
            model=self._config.model,
            timeout=self._config.llm_timeout,
        )
        self._runtime = AgentRuntime(self._config, llm)

        # All tools come from plugins — core has none built-in
        self._runtime.load_plugins()

        # Init deliberation with available tools
        tool_names = self._runtime._registry.names()
        self._deliberation = DeliberationEngine(tool_names)

        # Init execution engine
        self._execution = ExecutionEngine(
            permission_level=self._config.permission_level,
            safety=self._runtime._safety,
            logger=self._runtime._logger,
            workspace=self._config.output_dir,
        )

    def _print_banner(self) -> None:
        """Print startup banner."""
        rag_status = "not indexed (run: biopipe index samtools bwa fastqc)"
        try:
            from biopipe.rag.retriever import RAGRetriever
            rag = RAGRetriever(db_path=str(self._config.rag_db_path))
            if not rag.is_empty():
                rag_status = "ready"
        except Exception:
            rag_status = "unavailable (install: pip install chromadb)"

        plugins = self._runtime.status().loaded_plugins if self._runtime else ()
        plugin_str = ", ".join(plugins) if plugins else "none"

        print(_BANNER.format(
            model=self._config.model,
            rag_status=rag_status,
            plugins=plugin_str,
        ))

    def _handle_command(self, cmd: str) -> None:
        """Handle slash commands."""
        parts = cmd.split(maxsplit=1)
        command = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if command == "/help":
            print(_HELP)
        elif command == "/plan":
            self._show_plan()
        elif command == "/script":
            self._show_script()
        elif command == "/save":
            self._save_script(arg)
        elif command == "/execute":
            self._execute_script()
        elif command == "/reset":
            self._pipeline = PipelineState()
            print("Pipeline reset.")
        elif command == "/plugins":
            self._show_plugins()
        elif command == "/explain":
            self._handle_prompt(f"Explain the flag: {arg}")
        elif command in ("/quit", "/exit", "/q"):
            asyncio.run(self._runtime.shutdown())
            sys.exit(0)
        else:
            print(f"Unknown command: {command}. Type /help")

    def _handle_prompt(self, user_input: str) -> None:
        """Handle natural language prompt."""
        # Inject pipeline state into the prompt
        if not self._pipeline.is_empty():
            augmented = (
                f"{self._pipeline.format_for_llm()}\n\n"
                f"User request: {user_input}"
            )
        else:
            augmented = user_input

        try:
            result = asyncio.run(self._runtime.run(augmented))

            # Try to extract script from response and update pipeline state
            if "#!/" in result or "set -euo pipefail" in result:
                self._pipeline.update_script(result)

            print(f"\n{result}")

        except SafetyBlockedError as exc:
            print(f"\n SAFETY BLOCKED: {exc}")
        except BioPipeError as exc:
            print(f"\n Error: {exc}")

    def _show_plan(self) -> None:
        """Show current pipeline state."""
        if self._pipeline.is_empty():
            print("No pipeline built yet. Start with a request.")
            return
        print(self._pipeline.format_for_llm())

    def _show_script(self) -> None:
        """Show accumulated script."""
        if not self._pipeline.current_script:
            print("No script generated yet.")
            return
        print(self._pipeline.current_script)

    def _save_script(self, filename: str) -> None:
        """Save script to file."""
        if not self._pipeline.current_script:
            print("No script to save.")
            return
        fname = filename or "pipeline.sh"
        path = self._execution.save_script(self._pipeline.current_script, fname)
        print(f"Saved: {path}")

    def _execute_script(self) -> None:
        """Execute script with full approval flow."""
        if not self._pipeline.current_script:
            print("No script to execute.")
            return

        if not self._execution.can_execute():
            print("Execution disabled (dry-run mode).")
            print("To enable: export BIOPIPE_PERMISSION_LEVEL=EXECUTE")
            print("Script saved instead:")
            path = self._execution.save_script(
                self._pipeline.current_script, "pipeline.sh"
            )
            print(f"  {path}")
            return

        # Show script and ask for confirmation
        print("\n--- Script to execute ---")
        print(self._pipeline.current_script)
        print("--- End of script ---\n")

        try:
            confirm = input("Execute this script? [yes/NO] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nExecution cancelled.")
            return

        if confirm != "yes":
            print("Execution cancelled.")
            return

        # Create minimal plan for audit
        from biopipe.core.deliberation import ActionPlan, ProposedAction
        plan = ActionPlan(
            task_summary="User-requested execution",
            actions=[ProposedAction(
                tool_name="bash",
                action_description="Execute generated pipeline",
                justification="User explicitly requested execution",
                alternatives_considered=[],
            )],
            tools_available=self._runtime._registry.names(),
            tools_selected=["bash"],
            tools_rejected=[],
            overall_justification="User confirmed execution",
            estimated_output="Pipeline results in output directory",
        )
        self._deliberation.approve(plan)

        try:
            result = self._execution.execute(
                self._pipeline.current_script,
                plan=plan,
                user_confirmed=True,
            )
            if result.success:
                print(f"\nExecution completed (exit code: {result.exit_code})")
                if result.stdout:
                    print(result.stdout[:2000])
            else:
                print(f"\nExecution failed (exit code: {result.exit_code})")
                if result.stderr:
                    print(result.stderr[:2000])
        except (SafetyBlockedError, BioPipeError) as exc:
            print(f"\nBlocked: {exc}")

    def _show_plugins(self) -> None:
        """Show loaded plugins."""
        loaded = self._runtime.status().loaded_plugins if self._runtime else ()
        if not loaded:
            print("No plugins loaded.")
            print(f"Plugin directory: ~/.biopipe/plugins/")
            return
        for name in loaded:
            print(f"  - {name}")
