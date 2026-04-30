"""AgentRuntime: assembles all core components via dependency injection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from .config import Config
from .hooks import HookRegistry
from .logger import StructuredLogger
from .loop import AgentLoop
from .permissions import PermissionPolicy
from .router import Router
from .safety import SafetyValidator
from .session import SessionManager
from .tool_registry import ToolRegistry
from .tool_scheduler import ToolScheduler
from .types import Hook, LLMProvider, Tool
from typing import Any, Callable

@dataclass(frozen=True)
class RuntimeStatus:
    model: str
    rag_available: bool
    registered_tools: tuple[str, ...]
    loaded_plugins: tuple[str, ...]

class AgentRuntime:
    """Main controller. Assembles components, provides entry point."""

    def __init__(self, config: Config, llm: LLMProvider, system_prompt: str = "", rag: Any = None, rag_template: str = "{chunks}") -> None:
        self._config = config
        self._llm = llm
        self._logger = StructuredLogger(
            log_file=str(config.log_file) if config.log_file else None
        )
        self._registry = ToolRegistry()
        self._permissions = PermissionPolicy(config.permission_level)
        self._safety = SafetyValidator(
            allowlist=config.safety_allowlist,
            slurm_max_nodes=config.slurm_max_nodes,
            slurm_max_hours=config.slurm_max_hours,
        )
        self._hooks = HookRegistry()
        self._session = SessionManager(system_prompt, max_tokens=8192)
        self._scheduler = ToolScheduler(
            self._registry, self._permissions, timeout=config.llm_timeout
        )
        self._router = Router(self._registry)
        self._plugin_loader = None

        self._loop = AgentLoop(
            llm=llm,
            session=self._session,
            router=self._router,
            scheduler=self._scheduler,
            safety=self._safety,
            hooks=self._hooks,
            logger=self._logger,
            max_iterations=config.max_iterations,
            rag=rag,
            rag_top_k=config.rag_top_k,
            rag_template=rag_template,
        )



    async def run(self, user_input: str, stream_callback: Callable[[str], None] | None = None) -> str:
        """Process user input through the full agent loop."""
        self._logger.log("session_start", {"model": self._llm.model_id()})
        try:
            result = await self._loop.run(user_input, stream_callback=stream_callback)
            self._logger.log("session_end", {"status": "success"})
            return result
        except Exception as exc:
            self._logger.log("session_end", {"status": "error", "error": str(exc)})
            raise

    async def health_check(self) -> dict[str, bool]:
        """Check all subsystem health."""
        rag_ok = self._loop._rag is not None
        return {
            "llm": await self._llm.health_check(),
            "tools_registered": len(self._registry.names()) > 0,
            "rag_available": rag_ok,
        }

    def register_tool(self, tool: Tool) -> None:
        """Register a tool with integrity checks."""
        self._registry.register(tool)

    def register_hook(self, hook: Hook) -> None:
        """Register a hook at its declared point."""
        self._hooks.register(hook)

    def load_plugins(self) -> None:
        """Discover and load plugins from ~/.biopipe/plugins/."""
        from .plugin_sdk import PluginLoader
        from .errors import BioPipeError

        plugin_dir = str(Path.home() / ".biopipe" / "plugins")
        self._plugin_loader = PluginLoader(plugin_dir=plugin_dir)

        for manifest in self._plugin_loader.discover():
            try:
                result = self._plugin_loader.load_plugin(manifest)
                for tool in result["tools"]:
                    self.register_tool(tool)
                for hook in result["hooks"]:
                    self.register_hook(hook)
                self._logger.log("plugin_loaded", {
                    "name": manifest.name,
                    "version": manifest.version,
                    "tools": len(result["tools"]),
                    "hooks": len(result["hooks"]),
                })
            except BioPipeError as exc:
                self._logger.log("plugin_rejected", {
                    "name": manifest.name,
                    "error": str(exc),
                })

    def status(self) -> RuntimeStatus:
        loaded_plugins: tuple[str, ...] = ()
        if self._plugin_loader is not None:
            loaded_plugins = tuple(self._plugin_loader.list_loaded())
        return RuntimeStatus(
            model=self._llm.model_id(),
            rag_available=self._loop._rag is not None,
            registered_tools=tuple(self._registry.names()),
            loaded_plugins=loaded_plugins,
        )

    async def shutdown(self) -> None:
        """Graceful shutdown."""
        self._logger.close()
