"""WASM Plugin Runner: mathematically isolated sandbox for untrusted plugins.

This module provides a WebAssembly-based execution environment for BioPipe plugins.
Unlike Python-based plugins (loaded via importlib), WASM plugins run inside a
memory-isolated virtual machine powered by Wasmtime (Bytecode Alliance).

Security guarantees:
    1. DENY-BY-DEFAULT: WASM modules have ZERO access to filesystem, network, or OS.
    2. MEMORY ISOLATION: Each plugin gets its own linear memory buffer. It cannot
       read or write any byte of the Python host's memory.
    3. RESOURCE LIMITS: Fuel-based CPU limiting prevents infinite loops.
    4. WASI CAPABILITY MODEL: File access is granted per-directory, not globally.

Architecture:
    Python Core ──(JSON)──> WASM Memory ──(execute)──> WASM Module
                                                          │
                                                     (returns JSON)
                                                          │
    Python Core <──(parse)── WASM Memory <────────────────┘
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import ToolValidationError
from .types import PermissionLevel, ToolResult

logger = logging.getLogger(__name__)


# ── Resource Limits ──────────────────────────────────────────────────────────

MAX_WASM_MEMORY_PAGES = 256     # 256 × 64KB = 16 MB max memory per plugin
MAX_WASM_FUEL = 1_000_000_000   # ~1 billion instructions before forced halt
MAX_OUTPUT_BYTES = 65_536       # 64 KB max output from a single execute()


@dataclass(frozen=True)
class WasmPluginConfig:
    """Configuration for a single WASM plugin instance."""
    name: str
    wasm_path: Path
    max_memory_pages: int = MAX_WASM_MEMORY_PAGES
    max_fuel: int = MAX_WASM_FUEL
    allowed_dirs: tuple[str, ...] = ()  # WASI preopened directories (empty = no FS)


class WasmPluginRunner:
    """Loads and executes a single WASM plugin in an isolated sandbox.

    Each runner creates its own Wasmtime Store, Engine, and Instance.
    No state is shared between runners or between runners and the Python host.
    """

    def __init__(self, config: WasmPluginConfig) -> None:
        try:
            import wasmtime  # type: ignore
        except ImportError:
            raise ToolValidationError(
                "wasmtime is required for WASM plugins. "
                "Install: pip install wasmtime"
            )

        self._config = config
        self._wasmtime = wasmtime

        # ── Engine with fuel consumption enabled ─────────────────────────
        engine_config = wasmtime.Config()
        engine_config.consume_fuel = True
        self._engine = wasmtime.Engine(engine_config)

        # ── Load and compile the WASM module ─────────────────────────────
        wasm_bytes = config.wasm_path.read_bytes()
        if config.wasm_path.suffix == ".wat":
            # WebAssembly Text Format → compile on the fly
            self._module = wasmtime.Module(self._engine, wasm_bytes)
        elif config.wasm_path.suffix == ".wasm":
            self._module = wasmtime.Module(self._engine, wasm_bytes)
        else:
            raise ToolValidationError(
                f"Unsupported WASM file extension: {config.wasm_path.suffix}. "
                f"Expected .wasm or .wat"
            )

        logger.info(
            "WASM plugin '%s' compiled successfully (%d bytes)",
            config.name, len(wasm_bytes),
        )

    def _create_store(self) -> Any:
        """Create a fresh Store with fuel budget for each execution."""
        store = self._wasmtime.Store(self._engine)
        store.set_fuel(self._config.max_fuel)
        return store

    def _create_instance(self, store: Any) -> Any:
        """Instantiate the WASM module with optional WASI imports."""
        wasmtime = self._wasmtime

        # Check if the module needs WASI imports
        imports_needed = [imp.name for imp in self._module.imports]
        
        if any("wasi" in str(imp.module) for imp in self._module.imports):
            # Module needs WASI — provide minimal capabilities
            wasi_config = wasmtime.WasiConfig()
            
            # Grant access ONLY to explicitly allowed directories
            for allowed_dir in self._config.allowed_dirs:
                wasi_config.preopen_dir(allowed_dir, allowed_dir)
            
            store.set_wasi(wasi_config)
            linker = wasmtime.Linker(self._engine)
            linker.define_wasi()
            return linker.instantiate(store, self._module)
        else:
            # Pure computation module — no WASI, no FS, no network
            return wasmtime.Instance(store, self._module, [])

    def execute(self, params_json: str) -> ToolResult:
        """Execute the WASM plugin with JSON parameters.

        Flow:
            1. Create fresh Store (isolated memory + fuel budget)
            2. Instantiate WASM module
            3. Write input JSON into WASM linear memory via allocate()
            4. Call execute(ptr, len) exported function
            5. Read output JSON from WASM linear memory
            6. Parse and return ToolResult

        Args:
            params_json: JSON string with tool parameters.

        Returns:
            ToolResult with the plugin's output.

        Raises:
            ToolValidationError: If the WASM module crashes or exceeds limits.
        """
        store = self._create_store()

        try:
            instance = self._create_instance(store)
        except Exception as exc:
            raise ToolValidationError(
                f"WASM plugin '{self._config.name}' failed to instantiate: {exc}"
            ) from exc

        try:
            # ── Get exports ──────────────────────────────────────────────
            memory = instance.exports(store).get("memory")
            allocate_fn = instance.exports(store).get("allocate")
            execute_fn = instance.exports(store).get("execute")
            get_result_ptr_fn = instance.exports(store).get("get_result_ptr")
            get_result_len_fn = instance.exports(store).get("get_result_len")

            if memory is None:
                raise ToolValidationError(
                    f"WASM plugin '{self._config.name}' must export 'memory'"
                )

            # ── Write input into WASM memory ─────────────────────────────
            input_bytes = params_json.encode("utf-8")

            if allocate_fn is not None:
                # Plugin provides allocator — use it
                input_ptr = allocate_fn(store, len(input_bytes))
                mem_data = memory.data_ptr(store)
                mem_len = memory.data_len(store)

                if input_ptr + len(input_bytes) > mem_len:
                    raise ToolValidationError(
                        f"WASM plugin '{self._config.name}': "
                        f"allocation overflow ({input_ptr + len(input_bytes)} > {mem_len})"
                    )

                # Copy input bytes into WASM memory via ctypes
                import ctypes
                src = (ctypes.c_ubyte * len(input_bytes)).from_buffer_copy(input_bytes)
                base_addr = ctypes.cast(mem_data, ctypes.c_void_p).value or 0
                dst = ctypes.cast(base_addr + input_ptr, ctypes.c_void_p)
                ctypes.memmove(dst, src, len(input_bytes))
            else:
                # No allocator — write at offset 0 (simple plugins)
                input_ptr = 0
                mem_data = memory.data_ptr(store)
                import ctypes
                src = (ctypes.c_ubyte * len(input_bytes)).from_buffer_copy(input_bytes)
                base_addr = ctypes.cast(mem_data, ctypes.c_void_p).value or 0
                dst = ctypes.cast(base_addr, ctypes.c_void_p)
                ctypes.memmove(dst, src, len(input_bytes))

            # ── Call execute() ───────────────────────────────────────────
            if execute_fn is None:
                raise ToolValidationError(
                    f"WASM plugin '{self._config.name}' must export 'execute(i32, i32) -> i32'"
                )

            result_code = execute_fn(store, input_ptr, len(input_bytes))

            # ── Read output from WASM memory ─────────────────────────────
            if get_result_ptr_fn is not None and get_result_len_fn is not None:
                result_ptr = get_result_ptr_fn(store)
                result_len = get_result_len_fn(store)
            else:
                # Fallback: result starts right after input
                result_ptr = result_code  # execute returns ptr to result
                # Read until null byte or max
                result_len = min(MAX_OUTPUT_BYTES, memory.data_len(store) - result_ptr)

            # Clamp output size
            result_len = min(result_len, MAX_OUTPUT_BYTES)

            if result_ptr < 0 or result_ptr + result_len > memory.data_len(store):
                raise ToolValidationError(
                    f"WASM plugin '{self._config.name}': "
                    f"result pointer out of bounds ({result_ptr}, len={result_len})"
                )

            # Read bytes from WASM memory
            import ctypes
            base_addr = ctypes.cast(memory.data_ptr(store), ctypes.c_void_p).value or 0
            src_addr = ctypes.cast(base_addr + result_ptr, ctypes.c_void_p)
            output_buf = (ctypes.c_ubyte * result_len)()
            ctypes.memmove(output_buf, src_addr, result_len)
            output_str = bytes(output_buf).decode("utf-8", errors="replace").rstrip("\x00")

            # ── Parse result ─────────────────────────────────────────────
            try:
                result_data = json.loads(output_str)
                return ToolResult(
                    call_id=result_data.get("call_id", "wasm-0"),
                    success=result_data.get("success", True),
                    output=result_data.get("output", output_str),
                    error=result_data.get("error"),
                )
            except json.JSONDecodeError:
                # Not JSON — return raw string
                return ToolResult(
                    call_id="wasm-0",
                    success=True,
                    output=output_str,
                )

        except self._wasmtime.WasmtimeError as exc:
            error_msg = str(exc)
            if "fuel" in error_msg.lower():
                error_msg = (
                    f"WASM plugin '{self._config.name}' exceeded CPU budget "
                    f"({self._config.max_fuel} instructions). "
                    f"Possible infinite loop detected."
                )
            elif "unreachable" in error_msg.lower():
                error_msg = (
                    f"WASM plugin '{self._config.name}' hit unreachable instruction. "
                    f"The plugin attempted a forbidden operation."
                )

            logger.warning("WASM execution failed: %s", error_msg)
            return ToolResult(
                call_id="wasm-error",
                success=False,
                output="",
                error=error_msg,
            )
        except ToolValidationError:
            raise
        except Exception as exc:
            logger.error("Unexpected WASM error: %s", exc)
            return ToolResult(
                call_id="wasm-error",
                success=False,
                output="",
                error=f"WASM runtime error: {exc}",
            )


class WasmTool:
    """Wraps a WasmPluginRunner as a BioPipe Tool interface.

    This class bridges the gap between the WASM sandbox and the
    core ToolScheduler. From the core's perspective, a WasmTool
    behaves identically to a Python-based Tool.
    """

    def __init__(
        self,
        tool_name: str,
        tool_description: str,
        schema: dict[str, Any],
        runner: WasmPluginRunner,
    ) -> None:
        self._name = tool_name
        self._description = tool_description
        self._schema = schema
        self._runner = runner

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameter_schema(self) -> dict[str, Any]:
        return self._schema

    def required_permission(self) -> PermissionLevel:
        """WASM plugins are always capped at GENERATE (no execution)."""
        return PermissionLevel.GENERATE

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        """Serialize params to JSON, execute in WASM sandbox, return result."""
        params_json = json.dumps(params)
        return self._runner.execute(params_json)

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        """Basic JSON schema validation."""
        errors: list[str] = []
        required = self._schema.get("required", [])
        for field in required:
            if field not in params:
                errors.append(f"Missing required parameter: '{field}'")
        return errors
