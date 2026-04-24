# BioPipe-CLI Plugin Development Guide

## Overview

BioPipe-CLI plugins extend the agent's capabilities without modifying the core.
A plugin can add new **tools** (commands the AI can call) and **hooks**
(pre/post processing at defined points in the agent loop).

Every plugin runs inside the same safety sandbox as the core:
10-layer safety validation, permission cap at GENERATE, no network access.

## Quick Start (5 minutes)

### 1. Create plugin directory

```bash
mkdir -p ~/.biopipe/plugins/my-plugin
```

### 2. Create manifest.json

```json
{
  "name": "my-plugin",
  "version": "1.0.0",
  "author": "Your Name",
  "description": "Adds SLURM header generation to pipelines",
  "entry_point": "biopipe_plugin_slurm",
  "tools": ["SlurmHeaderTool"],
  "hooks": [],
  "permissions": ["read_docs"]
}
```

### 3. Create the Python package

```bash
mkdir -p ~/.biopipe/plugins/my-plugin/biopipe_plugin_slurm
touch ~/.biopipe/plugins/my-plugin/biopipe_plugin_slurm/__init__.py
```

### 4. Write the tool

```python
# ~/.biopipe/plugins/my-plugin/biopipe_plugin_slurm/__init__.py

from biopipe.core.types import PermissionLevel, ToolResult


class SlurmHeaderTool:
    """Generate SLURM #SBATCH headers for cluster submission."""

    @property
    def name(self) -> str:
        return "slurm_header"

    @property
    def description(self) -> str:
        return (
            "Generate a SLURM job submission header. "
            "Call this when the user wants to run a pipeline on an HPC cluster."
        )

    @property
    def parameter_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "job_name": {"type": "string", "description": "SLURM job name"},
                "nodes": {"type": "integer", "default": 1},
                "cpus": {"type": "integer", "default": 8},
                "memory_gb": {"type": "integer", "default": 32},
                "time_hours": {"type": "integer", "default": 12},
                "partition": {"type": "string", "default": "normal"},
            },
            "required": ["job_name"],
        }

    def required_permission(self) -> PermissionLevel:
        return PermissionLevel.GENERATE  # MUST be GENERATE or lower

    def validate_params(self, params: dict) -> list[str]:
        errors = []
        if "job_name" not in params:
            errors.append("job_name is required")
        if params.get("nodes", 1) > 4:
            errors.append("nodes cannot exceed 4 (safety limit)")
        if params.get("time_hours", 12) > 72:
            errors.append("time cannot exceed 72 hours (safety limit)")
        return errors

    async def execute(self, params: dict) -> ToolResult:
        job = params["job_name"]
        nodes = params.get("nodes", 1)
        cpus = params.get("cpus", 8)
        mem = params.get("memory_gb", 32)
        time_h = params.get("time_hours", 12)
        partition = params.get("partition", "normal")

        header = f"""#!/usr/bin/env bash
#SBATCH --job-name={job}
#SBATCH --nodes={nodes}
#SBATCH --cpus-per-task={cpus}
#SBATCH --mem={mem}G
#SBATCH --time={time_h}:00:00
#SBATCH --partition={partition}
#SBATCH --output={job}_%j.out
#SBATCH --error={job}_%j.err

set -euo pipefail
"""
        return ToolResult(
            call_id=params.get("_call_id", "slurm"),
            success=True,
            output=header,
            artifacts=[f"{job}_slurm.sh"],
        )
```

### 5. Install (add to Python path)

```bash
# Option A: pip install in development mode
cd ~/.biopipe/plugins/my-plugin
pip install -e .

# Option B: add to PYTHONPATH
export PYTHONPATH="$HOME/.biopipe/plugins/my-plugin:$PYTHONPATH"
```

### 6. Verify

```bash
biopipe plugins list
# Output:
#   my-plugin v1.0.0 — Adds SLURM header generation to pipelines
#     Tools: slurm_header
#     Hooks: (none)

biopipe interactive
> сгенерируй SLURM заголовок для RNA-seq анализа, 8 ядер, 64 ГБ
```

---

## Plugin Structure

```
~/.biopipe/plugins/
└── my-plugin/
    ├── manifest.json              # REQUIRED: plugin metadata
    ├── biopipe_plugin_slurm/      # Python package (matches entry_point)
    │   ├── __init__.py            # exports tool/hook classes
    │   └── templates/             # optional: data files
    ├── setup.py or pyproject.toml # optional: for pip install
    └── README.md                  # optional: documentation
```

---

## manifest.json Reference

```json
{
  "name": "plugin-name",
  "version": "1.0.0",
  "author": "Author Name <email>",
  "description": "What this plugin does (shown in `biopipe plugins list`)",
  "entry_point": "python_package_name",
  "tools": ["ClassName1", "ClassName2"],
  "hooks": ["HookClassName1"],
  "permissions": ["read_docs"]
}
```

### Fields

| Field | Required | Description |
|---|---|---|
| `name` | yes | Unique plugin identifier |
| `version` | yes | Semver version string |
| `author` | yes | Author name |
| `description` | yes | One-line description |
| `entry_point` | yes | Python importable package name |
| `tools` | no | List of Tool class names exported from entry_point |
| `hooks` | no | List of Hook class names exported from entry_point |
| `permissions` | no | List of requested capabilities |

### Permissions

Allowed permissions:
- `read_docs` — read documentation files
- `read_workspace` — read files in project directory
- `generate` — generate scripts (default for all tools)

**Forbidden permissions** (plugin will be rejected at load time):
- `execute` — run scripts
- `network` — make HTTP/socket calls
- `write_system` — write outside workspace
- `modify_core` — patch core modules
- `escalate_permission` — request higher permissions at runtime
- `disable_safety` — bypass safety validator
- `access_env` — read environment variables
- `raw_llm` — call LLM directly bypassing safety

---

## Writing a Tool

A tool is any Python class that implements the `Tool` protocol:

```python
from biopipe.core.types import PermissionLevel, ToolResult

class MyTool:
    @property
    def name(self) -> str:
        """Unique tool name. Used by LLM to call this tool."""
        return "my_tool_name"

    @property
    def description(self) -> str:
        """Description shown to LLM in function calling schema.
        Be specific — this is how the LLM decides when to use your tool."""
        return "Does X when the user asks for Y"

    @property
    def parameter_schema(self) -> dict:
        """JSON Schema for parameters. Must have 'type' key."""
        return {
            "type": "object",
            "properties": {
                "param1": {"type": "string", "description": "What this param does"},
            },
            "required": ["param1"],
        }

    def required_permission(self) -> PermissionLevel:
        """MUST return GENERATE or READ_ONLY. Never EXECUTE."""
        return PermissionLevel.GENERATE

    def validate_params(self, params: dict) -> list[str]:
        """Return list of error strings. Empty list = valid."""
        errors = []
        if "param1" not in params:
            errors.append("param1 is required")
        return errors

    async def execute(self, params: dict) -> ToolResult:
        """Generate output. NEVER execute system commands here."""
        result = f"Generated output for {params['param1']}"
        return ToolResult(
            call_id=params.get("_call_id", "my_tool"),
            success=True,
            output=result,
        )
```

### Rules for Tools

1. **`required_permission()` MUST return `GENERATE` or `READ_ONLY`.**
   Returning `EXECUTE` or `WRITE_WORKSPACE` → plugin rejected at load time.

2. **Never call `os.system()`, `subprocess`, `socket`, or any I/O.**
   Your tool generates text, not executes commands. If you need to read
   a local file, use `open()` with read-only mode on files within the
   workspace only.

3. **Never import `os`, `subprocess`, `shutil`, `socket`, `urllib`.**
   The AST analyzer will flag these in safety validation.

4. **`parameter_schema` must be valid JSON Schema with `"type"` key.**
   The LLM uses this schema for function calling. Bad schema = tool
   never gets called.

5. **`description` is critical.** The LLM decides which tool to use based
   on description. Be specific: "Generate SLURM headers for HPC job
   submission" is better than "SLURM helper".

---

## Writing a Hook

Hooks run at defined points in the agent loop. They can inspect or modify
the context at each point.

```python
from biopipe.core.types import HookPoint

class MyHook:
    def hook_point(self) -> HookPoint:
        """When this hook fires."""
        return HookPoint.BEFORE_SCRIPT_OUTPUT

    async def run(self, context: dict) -> dict | None:
        """Process context. Return None to pass through, dict to modify."""
        script = context.get("output", "")

        # Example: add a comment header to every script
        if script and not script.startswith("# Plugin:"):
            context["output"] = f"# Plugin: my-plugin\n{script}"
            return context

        return None  # pass through unchanged
```

### Hook Points

| HookPoint | When it fires | Context keys |
|---|---|---|
| `BEFORE_LLM_CALL` | Before sending messages to LLM | `messages`, `iteration` |
| `AFTER_LLM_CALL` | After LLM responds | `response` |
| `BEFORE_TOOL_EXECUTE` | Before running a tool | `tool_call`, `tool` |
| `AFTER_TOOL_EXECUTE` | After tool returns | `tool_result` |
| `BEFORE_SCRIPT_OUTPUT` | Before showing script to user | `output`, `safety_report` |
| `ON_ERROR` | When an error occurs | `error`, `traceback` |

### Rules for Hooks

1. **Return `None` to pass through.** Returning `None` means "I didn't
   change anything, continue normally."

2. **Return a modified `dict` to change context.** The returned dict
   replaces the context for downstream hooks and the next step.

3. **Never block.** Hooks should complete in <100ms. No network calls,
   no heavy computation.

4. **Hooks see ALL output.** A hook at `BEFORE_SCRIPT_OUTPUT` sees
   every script before the user. This is powerful — use responsibly.

---

## Example Plugins

### SLURM Header Generator
Adds `#SBATCH` headers to scripts for HPC submission.
See the Quick Start example above.

### ShellCheck Validator Hook
Runs ShellCheck on generated bash scripts before output.

```python
# biopipe_plugin_shellcheck/__init__.py

import subprocess
from biopipe.core.types import HookPoint

class ShellCheckHook:
    def hook_point(self) -> HookPoint:
        return HookPoint.BEFORE_SCRIPT_OUTPUT

    async def run(self, context: dict) -> dict | None:
        script = context.get("output", "")
        if not script or "#!/" not in script:
            return None

        try:
            result = subprocess.run(
                ["shellcheck", "-s", "bash", "-"],
                input=script, capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                warnings = result.stdout.strip()
                context["output"] = (
                    f"{script}\n\n"
                    f"# ---- ShellCheck Warnings ----\n"
                    f"# {warnings}\n"
                )
                return context
        except FileNotFoundError:
            pass  # shellcheck not installed, skip silently

        return None
```

### Conda Environment Generator
Generates `environment.yml` alongside pipeline scripts.

### Singularity Wrapper
Wraps tool calls in `singularity exec` for containerized HPC.

---

## Testing Your Plugin

```python
# tests/test_my_plugin.py
import asyncio
import pytest
from biopipe_plugin_slurm import SlurmHeaderTool
from biopipe.core.types import PermissionLevel

def test_permission_is_generate():
    tool = SlurmHeaderTool()
    assert tool.required_permission() == PermissionLevel.GENERATE

def test_schema_has_type():
    tool = SlurmHeaderTool()
    assert "type" in tool.parameter_schema

def test_validate_missing_job_name():
    tool = SlurmHeaderTool()
    errors = tool.validate_params({})
    assert len(errors) > 0

def test_generate_header():
    tool = SlurmHeaderTool()
    result = asyncio.run(tool.execute({"job_name": "rnaseq_01"}))
    assert result.success
    assert "#SBATCH" in result.output
    assert "rnaseq_01" in result.output

def test_safety_limits():
    tool = SlurmHeaderTool()
    errors = tool.validate_params({"job_name": "x", "nodes": 9999})
    assert any("cannot exceed" in e for e in errors)
```

Run:
```bash
cd ~/.biopipe/plugins/my-plugin
pip install -e .
pytest tests/ -v
```

---

## Security Model

```
Plugin Code
    │
    ▼
manifest.json validation ──→ forbidden permission? → REJECTED
    │
    ▼
Tool class validation ──→ required_permission > GENERATE? → REJECTED
    │                  ──→ overrides __getattr__/__setattr__? → REJECTED
    │                  ──→ invalid parameter_schema? → REJECTED
    │
    ▼
Registered in ToolRegistry
    │
    ▼
LLM calls tool ──→ ToolScheduler validates params
    │             ──→ PermissionPolicy checks level
    │
    ▼
Tool.execute() runs
    │
    ▼
Output passes through SafetyValidator (10 layers)
    │
    ▼
User sees result
```

**Key guarantee:** no matter what a plugin does inside `execute()`,
the output passes through the same 10-layer SafetyValidator as core output.
If a plugin generates `rm -rf /`, safety blocks it. If a plugin generates
`curl http://evil.com`, safety blocks it. The plugin cannot bypass safety.

---

## CLI Commands for Plugins

```bash
# List installed plugins
biopipe plugins list

# Show plugin details
biopipe plugins info my-plugin

# Validate a plugin before installing
biopipe plugins validate ~/.biopipe/plugins/my-plugin

# (Future) Install from community registry
# biopipe plugins install biopipe-plugin-slurm
```

---

## FAQ

**Q: Can my plugin execute system commands?**
A: No. `required_permission()` is capped at `GENERATE`. Even if you call
`subprocess.run()` inside `execute()`, the ToolRegistry validates at load
time and SafetyValidator checks output. But don't do it — it violates
the trust model and future versions may sandbox plugins in a subprocess.

**Q: Can my plugin call the LLM directly?**
A: No. `raw_llm` is a forbidden permission. Plugins generate text
deterministically or use templates. If you need LLM reasoning, create
a tool that the LLM calls naturally through the agent loop.

**Q: Can my plugin read files?**
A: Yes, with `read_workspace` or `read_docs` permission. Only files
inside the project workspace. Never system files, never home directory.

**Q: Can my plugin modify the safety validator?**
A: No. `disable_safety` and `modify_core` are forbidden. The safety
validator is immutable from plugin perspective.

**Q: How does the LLM know about my plugin?**
A: Your tool's `name`, `description`, and `parameter_schema` are
automatically added to the LLM's function calling schema via
`ToolRegistry.list_schemas()`. The LLM sees your tool alongside
built-in tools and decides when to call it based on `description`.

**Q: Can I publish my plugin?**
A: Yes. Package it as a pip-installable package, host on PyPI or GitHub.
Users install with `pip install biopipe-plugin-slurm` and add the
plugin to `~/.biopipe/plugins/`. A community registry is planned.
