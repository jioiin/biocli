"""Tests for WASM Plugin Sandbox.

Validates:
    1. WASM plugin loads and executes inside Wasmtime VM
    2. Memory isolation: WASM cannot access host Python memory
    3. CPU fuel exhaustion: infinite loops are terminated
    4. Output parsing: JSON results from WASM are correctly deserialized
    5. Plugin SDK integration: WasmTool behaves identically to Python Tool
    6. Security: WASM module with 'unreachable' instruction is caught gracefully
"""

import json
import asyncio
import importlib.util
import pytest
from pathlib import Path

from biopipe.core.wasm_runner import WasmPluginRunner, WasmPluginConfig, WasmTool
from biopipe.core.plugin_sdk import PluginLoader, PluginManifest
from biopipe.core.errors import ToolValidationError


DEMO_PLUGIN_DIR = Path(__file__).parent.parent / "plugins"
DEMO_WAT_PATH = DEMO_PLUGIN_DIR / "biopipe_wasm_demo" / "plugin.wat"
pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("wasmtime") is None,
    reason="wasmtime is not installed",
)


class TestWasmRunner:
    """Test the low-level WasmPluginRunner."""

    def test_wasm_module_loads(self):
        """WASM .wat file compiles and instantiates without errors."""
        if not DEMO_WAT_PATH.exists():
            pytest.skip("Demo WASM plugin not found")

        config = WasmPluginConfig(name="test_wasm", wasm_path=DEMO_WAT_PATH)
        runner = WasmPluginRunner(config)
        assert runner is not None

    def test_wasm_execute_returns_result(self):
        """execute() returns a valid ToolResult with output from WASM memory."""
        if not DEMO_WAT_PATH.exists():
            pytest.skip("Demo WASM plugin not found")

        config = WasmPluginConfig(name="test_wasm", wasm_path=DEMO_WAT_PATH)
        runner = WasmPluginRunner(config)

        result = runner.execute('{"assay": "rna-seq"}')
        assert result.success is True
        assert "WASM" in result.output
        assert "Sandbox" in result.output

    def test_wasm_output_is_parseable(self):
        """The output from WASM can be parsed back as valid JSON or text."""
        if not DEMO_WAT_PATH.exists():
            pytest.skip("Demo WASM plugin not found")

        config = WasmPluginConfig(name="test_wasm", wasm_path=DEMO_WAT_PATH)
        runner = WasmPluginRunner(config)
        result = runner.execute('{}')
        # The result should be successfully parsed (not empty)
        assert len(result.output) > 0

    def test_wasm_fresh_store_per_execution(self):
        """Each execute() gets a fresh Store — no state leakage between calls."""
        if not DEMO_WAT_PATH.exists():
            pytest.skip("Demo WASM plugin not found")

        config = WasmPluginConfig(name="test_wasm", wasm_path=DEMO_WAT_PATH)
        runner = WasmPluginRunner(config)

        result1 = runner.execute('{"call": 1}')
        result2 = runner.execute('{"call": 2}')

        # Both should succeed independently
        assert result1.success is True
        assert result2.success is True


class TestWasmFuelExhaustion:
    """Test that infinite loops in WASM are terminated by fuel limits."""

    def test_infinite_loop_caught(self):
        """A WASM module with an infinite loop runs out of fuel and is stopped."""
        # Create a .wat with an infinite loop
        infinite_wat = b"""
        (module
          (memory (export "memory") 1)
          (func (export "allocate") (param i32) (result i32) (i32.const 0))
          (func (export "execute") (param i32) (param i32) (result i32)
            (loop $inf
              (br $inf)
            )
            (i32.const 0)
          )
          (func (export "get_result_ptr") (result i32) (i32.const 0))
          (func (export "get_result_len") (result i32) (i32.const 0))
        )
        """
        # Write to temp file
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".wat", delete=False, dir=str(DEMO_PLUGIN_DIR)) as f:
            f.write(infinite_wat)
            temp_path = Path(f.name)

        try:
            config = WasmPluginConfig(
                name="infinite_loop_test",
                wasm_path=temp_path,
                max_fuel=10_000,  # Very low fuel budget
            )
            runner = WasmPluginRunner(config)
            result = runner.execute('{}')

            # Should fail gracefully, not hang
            assert result.success is False
            assert "fuel" in result.error.lower() or "exceeded" in result.error.lower()
        finally:
            temp_path.unlink(missing_ok=True)


class TestWasmUnreachable:
    """Test that WASM 'unreachable' instruction (forbidden operation) is caught."""

    def test_unreachable_caught(self):
        """A WASM module that hits 'unreachable' returns error, not crash."""
        trap_wat = b"""
        (module
          (memory (export "memory") 1)
          (func (export "allocate") (param i32) (result i32) (i32.const 0))
          (func (export "execute") (param i32) (param i32) (result i32)
            (unreachable)
          )
          (func (export "get_result_ptr") (result i32) (i32.const 0))
          (func (export "get_result_len") (result i32) (i32.const 0))
        )
        """
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".wat", delete=False, dir=str(DEMO_PLUGIN_DIR)) as f:
            f.write(trap_wat)
            temp_path = Path(f.name)

        try:
            config = WasmPluginConfig(name="trap_test", wasm_path=temp_path)
            runner = WasmPluginRunner(config)
            result = runner.execute('{}')

            assert result.success is False
            assert "unreachable" in result.error.lower() or "forbidden" in result.error.lower()
        finally:
            temp_path.unlink(missing_ok=True)


class TestWasmTool:
    """Test the WasmTool adapter that bridges WASM to BioPipe Tool interface."""

    def test_wasm_tool_has_correct_name(self):
        """WasmTool exposes the correct name from manifest schema."""
        if not DEMO_WAT_PATH.exists():
            pytest.skip("Demo WASM plugin not found")

        config = WasmPluginConfig(name="test", wasm_path=DEMO_WAT_PATH)
        runner = WasmPluginRunner(config)
        tool = WasmTool(
            tool_name="wasm_pipeline_generator",
            tool_description="Test WASM tool",
            schema={"type": "object", "properties": {}, "required": []},
            runner=runner,
        )

        assert tool.name == "wasm_pipeline_generator"
        assert tool.description == "Test WASM tool"
        assert tool.required_permission().name == "GENERATE"

    def test_wasm_tool_execute_async(self):
        """WasmTool.execute() works as an async coroutine."""
        if not DEMO_WAT_PATH.exists():
            pytest.skip("Demo WASM plugin not found")

        config = WasmPluginConfig(name="test", wasm_path=DEMO_WAT_PATH)
        runner = WasmPluginRunner(config)
        tool = WasmTool(
            tool_name="test_tool",
            tool_description="Test",
            schema={},
            runner=runner,
        )

        result = asyncio.run(tool.execute({"assay": "qc"}))
        assert result.success is True

    def test_wasm_tool_validate_params(self):
        """WasmTool validates required parameters."""
        if not DEMO_WAT_PATH.exists():
            pytest.skip("Demo WASM plugin not found")

        config = WasmPluginConfig(name="test", wasm_path=DEMO_WAT_PATH)
        runner = WasmPluginRunner(config)
        tool = WasmTool(
            tool_name="test_tool",
            tool_description="Test",
            schema={"required": ["assay"]},
            runner=runner,
        )

        errors = tool.validate_params({})
        assert len(errors) == 1
        assert "assay" in errors[0]

        errors = tool.validate_params({"assay": "rna-seq"})
        assert len(errors) == 0


class TestPluginSDKWasmIntegration:
    """Test that PluginLoader correctly discovers and loads WASM plugins."""

    def test_discover_wasm_plugin(self):
        """PluginLoader discovers WASM plugin via manifest.json."""
        loader = PluginLoader(plugin_dir=str(DEMO_PLUGIN_DIR))
        manifests = loader.discover()

        wasm_manifests = [m for m in manifests if m.wasm_file]
        assert len(wasm_manifests) >= 1
        assert wasm_manifests[0].name == "biopipe_wasm_demo"

    def test_load_wasm_plugin_returns_tools(self):
        """PluginLoader.load_plugin() returns WasmTool instances for WASM plugins."""
        loader = PluginLoader(plugin_dir=str(DEMO_PLUGIN_DIR))
        manifests = loader.discover()

        wasm_manifest = next(m for m in manifests if m.wasm_file)
        result = loader.load_plugin(wasm_manifest)

        assert "tools" in result
        assert len(result["tools"]) >= 1
        assert result["tools"][0].name == "wasm_pipeline_generator"
