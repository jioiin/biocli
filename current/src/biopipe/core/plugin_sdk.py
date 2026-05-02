"""Plugin SDK: community-extensible plugin system for BioPipe-CLI.

Plugins are Python packages that expose tools, hooks, or generators.
Each plugin has a manifest (dict) declaring capabilities and permissions.

Security: plugins CANNOT exceed GENERATE permission, CANNOT override
core modules, CANNOT access network. All plugin outputs pass through
the same SafetyValidator as core-generated code.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import PermissionDeniedError, ToolValidationError
from .types import Hook, PermissionLevel, Tool


@dataclass(frozen=True)
class PluginManifest:
    """Plugin metadata and security declaration."""
    name: str
    version: str
    author: str
    description: str
    tools: list[str] = field(default_factory=list)
    hooks: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    entry_point: str = ""  # e.g., "biopipe_plugin_slurm.main"
    wasm_file: str = ""    # e.g., "plugin.wasm" — if set, uses WASM sandbox
    wasm_tool_schemas: list[dict] = field(default_factory=list)  # tool schemas for WASM plugins


# Capabilities a plugin can NEVER request
_FORBIDDEN_CAPABILITIES: frozenset[str] = frozenset({
    "execute",           # no script execution
    "network",           # no network access
    "write_system",      # no writing outside workspace
    "modify_core",       # no patching core modules
    "escalate_permission",
    "disable_safety",
    "access_env",        # no os.environ reading
    "raw_llm",           # no direct LLM calls bypassing safety
})


class PluginLoader:
    """Load, validate, and register plugins."""

    def __init__(self, plugin_dir: str | None = None) -> None:
        self._plugin_dir = Path(plugin_dir) if plugin_dir else None
        self._loaded: dict[str, PluginManifest] = {}

    def discover(self) -> list[PluginManifest]:
        """Discover plugins from plugin directory."""
        if not self._plugin_dir or not self._plugin_dir.exists():
            return []

        manifests: list[PluginManifest] = []
        for manifest_path in self._plugin_dir.glob("*/manifest.json"):
            try:
                manifest = self._load_manifest(manifest_path)
                self._validate_manifest(manifest)
                manifests.append(manifest)
            except (ToolValidationError, PermissionDeniedError, json.JSONDecodeError):
                continue

        return manifests

    # System modules that MUST NOT be importable as plugins
    _BLOCKED_ENTRY_POINTS: frozenset[str] = frozenset({
        "os", "sys", "subprocess", "shutil", "socket",
        "http", "urllib", "requests", "pathlib",
        "pickle", "marshal", "ctypes", "importlib",
        "code", "codeop", "runpy", "builtins",
    })

    def load_plugin(self, manifest: PluginManifest) -> dict[str, Any]:
        """Load a plugin and return its tools and hooks.

        Supports two loading modes:
        1. WASM sandbox (if manifest.wasm_file is set) — mathematically isolated
        2. Python import (legacy, if manifest.entry_point is set) — importlib-based
        """
        self._validate_manifest(manifest)

        # ── WASM Plugin Loading ──────────────────────────────────────────
        if manifest.wasm_file:
            return self._load_wasm_plugin(manifest)

        # ── Python Plugin Loading (Trusted-only disabled by default) ─────
        if manifest.entry_point:
            raise PermissionDeniedError(
                f"Plugin '{manifest.name}' uses Python entry_point plugins, which are disabled. "
                "Use WASM plugins for sandboxed third-party execution."
            )

        if not manifest.entry_point:
            raise ToolValidationError(
                f"Plugin '{manifest.name}' has no entry_point and no wasm_file"
            )

        # SECURITY: block system modules as entry points
        root_module = manifest.entry_point.split(".")[0]
        if root_module in self._BLOCKED_ENTRY_POINTS:
            raise ToolValidationError(
                f"Plugin '{manifest.name}' entry_point '{manifest.entry_point}' "
                f"resolves to blocked system module '{root_module}'."
            )

        # SECURITY: entry_point must start with biopipe_ prefix
        if not root_module.startswith(("biopipe_", "biopipe-")):
            raise ToolValidationError(
                f"Plugin entry_point must start with 'biopipe_' prefix. "
                f"Got: '{manifest.entry_point}'. "
                f"This prevents importing arbitrary Python modules."
            )

        try:
            module = importlib.import_module(manifest.entry_point)
        except ImportError as exc:
            raise ToolValidationError(
                f"Cannot import plugin '{manifest.name}': {exc}"
            ) from exc

        tools: list[Tool] = []
        hooks: list[Hook] = []

        # Collect tools
        for tool_name in manifest.tools:
            tool_class = getattr(module, tool_name, None)
            if tool_class is None:
                raise ToolValidationError(
                    f"Plugin '{manifest.name}' declares tool '{tool_name}' "
                    f"but it's not found in {manifest.entry_point}"
                )
            tool_instance = tool_class()
            self._validate_tool(tool_instance, manifest.name)
            tools.append(tool_instance)

        # Collect hooks
        for hook_name in manifest.hooks:
            hook_class = getattr(module, hook_name, None)
            if hook_class is None:
                raise ToolValidationError(
                    f"Plugin '{manifest.name}' declares hook '{hook_name}' "
                    f"but it's not found in {manifest.entry_point}"
                )
            hooks.append(hook_class())

        self._loaded[manifest.name] = manifest
        return {"tools": tools, "hooks": hooks}

    def _load_wasm_plugin(self, manifest: PluginManifest) -> dict[str, Any]:
        """Load a WASM-sandboxed plugin.

        The plugin runs inside a Wasmtime VM with:
        - Zero filesystem access (unless explicitly granted)
        - Zero network access
        - CPU fuel budget (prevents infinite loops)
        - Linear memory isolation (cannot read host memory)
        """
        from .wasm_runner import WasmPluginRunner, WasmPluginConfig, WasmTool

        # Resolve WASM file path relative to the plugin directory
        if self._plugin_dir:
            wasm_path = self._plugin_dir / manifest.name / manifest.wasm_file
        else:
            wasm_path = Path(manifest.wasm_file)

        if not wasm_path.exists():
            raise ToolValidationError(
                f"WASM file not found for plugin '{manifest.name}': {wasm_path}"
            )

        config = WasmPluginConfig(
            name=manifest.name,
            wasm_path=wasm_path,
        )
        runner = WasmPluginRunner(config)

        # Create WasmTool instances from manifest schemas
        tools = []
        for schema in manifest.wasm_tool_schemas:
            tool = WasmTool(
                tool_name=schema.get("name", manifest.name),
                tool_description=schema.get("description", manifest.description),
                schema=schema.get("parameters", {}),
                runner=runner,
            )
            tools.append(tool)

        # If no schemas provided, create a default tool
        if not tools:
            tool = WasmTool(
                tool_name=manifest.name,
                tool_description=manifest.description,
                schema={},
                runner=runner,
            )
            tools.append(tool)

        self._loaded[manifest.name] = manifest
        return {"tools": tools, "hooks": []}

    def list_loaded(self) -> list[str]:
        """List names of loaded plugins."""
        return list(self._loaded.keys())

    @staticmethod
    def _load_manifest(path: Path) -> PluginManifest:
        """Parse manifest.json into PluginManifest."""
        data = json.loads(path.read_text(encoding="utf-8"))
        return PluginManifest(
            name=data["name"],
            version=data.get("version", "0.0.0"),
            author=data.get("author", "unknown"),
            description=data.get("description", ""),
            tools=data.get("tools", []),
            hooks=data.get("hooks", []),
            permissions=data.get("permissions", []),
            entry_point=data.get("entry_point", ""),
            wasm_file=data.get("wasm_file", ""),
            wasm_tool_schemas=data.get("wasm_tool_schemas", []),
        )

    @staticmethod
    def _validate_manifest(manifest: PluginManifest) -> None:
        """Check manifest for forbidden capabilities."""
        for perm in manifest.permissions:
            if perm.lower() in _FORBIDDEN_CAPABILITIES:
                raise PermissionDeniedError(
                    f"Plugin '{manifest.name}' requests forbidden "
                    f"capability: '{perm}'. This is blocked by security policy."
                )

    @staticmethod
    def _validate_tool(tool: Tool, plugin_name: str) -> None:
        """Validate individual tool from plugin."""
        if tool.required_permission().value > PermissionLevel.GENERATE.value:
            raise PermissionDeniedError(
                f"Tool '{tool.name}' from plugin '{plugin_name}' "
                f"requests {tool.required_permission().name}. "
                f"Max allowed: GENERATE."
            )
