# BioPipe-CLI — Project Context for AI Auditors

This document provides full context for any AI system reviewing, auditing,
or analyzing BioPipe-CLI code. Read this BEFORE analyzing any source files.

---

## What is BioPipe-CLI

BioPipe-CLI is a local CLI agent that helps bioinformatics scientists generate
bash/python scripts for genomic data analysis pipelines. The scientist types
a request in natural language ("make an RNA-seq pipeline for mouse, paired-end,
mm39 genome"), and the agent generates a ready-to-run script with correct tools,
parameters, and comments.

**It is NOT a web app, NOT a cloud service, NOT a GUI application.**
It is a terminal program that runs entirely on the scientist's machine.

---

## Core Principle: LLM = Untrusted Text Generator

The local LLM (running via llama.cpp or Ollama) is treated as an **untrusted
text generator**. It produces text that might contain:
- Dangerous commands (rm -rf, sudo, curl)
- Hallucinated tool flags that don't exist
- Incorrect parameters for bioinformatics tools
- Prompt injection attempts passed through from user input

Therefore, ALL LLM output passes through a deterministic Python safety
validator (10 layers) BEFORE the user sees it. The LLM cannot bypass safety
because safety is Python code, not an LLM instruction.

---

## Architecture Overview

```
User Input
  → InputSandbox (strip injection tags, score risk)
  → SessionManager (add to conversation history)
  → AgentLoop:
      → RAG Retriever (fetch relevant documentation from ChromaDB)
      → LLM.generate(messages + RAG context + tool schemas)
      → If LLM returns text → SafetyValidator → User
      → If LLM returns tool_calls:
          → Router → resolve tool from ToolRegistry
          → PermissionPolicy → check permission ≤ GENERATE
          → ToolScheduler → execute tool
          → SafetyValidator → check tool output (10 layers)
          → Add result to messages → REPEAT loop
      → max_iterations = 10 (prevent infinite loops)
```

---

## Module Map (30 core modules)

### Security Layer
- `types.py` — All Protocol/ABC/dataclass contracts. Frozen types for ToolCall, SafetyViolation
- `errors.py` — Exception hierarchy (BioPipeError → specific errors)
- `config.py` — Frozen dataclass. Validates localhost-only URL, blocks cloud models
- `sandbox.py` — Input sanitization. Strips LLM instruction tags, scores injection risk
- `ast_analyzer.py` — Python AST analysis. Blocks os.system, subprocess, pickle, eval
- `path_validator.py` — Blocks path traversal (../, /etc/, ~/.bashrc)
- `safety.py` — **10-layer output validator**. Every LLM output passes through ALL 10 layers
- `permissions.py` — Immutable permission policy. __slots__ + __setattr__ override. Max = GENERATE

### Agent Infrastructure
- `tool_registry.py` — Stores registered tools. Generates JSON schemas for LLM function calling
- `tool_scheduler.py` — Sequential tool execution with timeout and validation
- `hooks.py` — Pre/post hooks at 6 points in the agent loop
- `router.py` — Maps tool_name from LLM → concrete Tool from registry
- `session.py` — Conversation history. Compaction at 75% context. Injection-safe restore()
- `loop.py` — Agent loop: prompt → LLM → tool calls → safety → output. ~60 lines
- `runtime.py` — Dependency injection container. Assembles all subsystems
- `logger.py` — Structured JSON logging. Redacts API keys, truncates large values

### Agent Capabilities
- `pipeline_state.py` — Accumulated script that survives session compaction
- `plugin_sdk.py` — Plugin loader. Validates manifest, blocks forbidden capabilities, requires biopipe_ prefix
- `deliberation.py` — AI must justify tool selection before execution
- `execution.py` — 4-gate execution: permission → plan approved → safety passed → user confirmed
- `workspace.py` — Scans project directory for FASTQ, BAM, VCF files
- `shell_tool.py` — Whitelisted read-only commands (ls, find, head, which)
- `system_profiler.py` — Detects CPU, RAM, installed bioinformatics tools
- `git_tool.py` — Local-only git operations (no push/pull/fetch)
- `memory.py` — Persistent memory across sessions (~/.biopipe/memory.json)
- `task_decomposer.py` — Breaks "full WGS analysis" into 7 ordered substeps
- `tool_selection.py` — Deterministic rules: RNA-seq → HISAT2/STAR, WGS → BWA
- `project_context.py` — Reads BIOPIPE.md (project config, like CLAUDE.md for Claude Code)
- `audit.py` — Exports audit trail as JSON (21 CFR Part 11) and Markdown (NIH DMS)
- `error_recovery.py` — Parses stderr patterns, suggests fixes for common bioinformatics errors

### LLM Adapters
- `llm/base.py` — MockLLM for testing
- `llm/ollama.py` — Ollama HTTP adapter (localhost only)
- `llm/llamacpp_embedded.py` — Direct llama.cpp via Python bindings. Zero HTTP, zero telemetry
- `llm/prompts.py` — System prompts for the LLM

### RAG (Retrieval-Augmented Generation)
- `rag/chunker.py` — Splits man pages by sections (SYNOPSIS, OPTIONS, EXAMPLES)
- `rag/indexer.py` — Indexes tool documentation into ChromaDB
- `rag/retriever.py` — Hybrid search: BM25 + vector similarity

### Interface
- `cli.py` — Typer CLI app (generate, index, setup, health, interactive, plugins)
- `repl.py` — Interactive REPL with slash commands (/plan, /script, /save, /execute)
- `setup_wizard.py` — Auto-download verified model from HuggingFace, test inference

---

## Security Model

### What is immutable (cannot be changed at runtime)
- `Config` — frozen=True dataclass
- `PermissionPolicy.system_level` — __slots__ + __setattr__ override
- `SafetyValidator._allowlist` — frozenset
- `ToolCall` — frozen=True dataclass
- `SafetyViolation` — frozen=True dataclass
- `PluginManifest` — frozen=True dataclass

### What is blocked
- Cloud models (name contains "-cloud") → ValueError at config load
- Remote ollama_url (not localhost) → ValueError at config load
- Plugin entry_point = system module (os, subprocess, socket) → ToolValidationError
- Plugin entry_point without "biopipe_" prefix → ToolValidationError
- Plugin requesting forbidden capability (execute, network, disable_safety) → PermissionDeniedError
- Tool requesting permission > GENERATE → PermissionDeniedError
- Injected SYSTEM messages in session restore → silently skipped
- Dangerous tools in allowlist (rm, sudo, curl, wget) → filtered at config load

### 10 Safety Layers (every LLM output passes through ALL 10)
1. Regex blocklist: rm -rf, sudo, chmod 777, eval, dd, mkfs
2. Obfuscation detection: base64 decode | sh, $'\x72m', variable-based evasion
3. Network blocking: curl, wget, ping exfiltration, python socket/requests
4. Dependency squatting: pip install, conda install, apt-get install
5. Path traversal: ../, ~/.bashrc, /etc/, /dev/sd
6. SLURM resource limits: nodes ≤ 4, time ≤ 72h, mem ≤ 256G
7. Unquoted variables: $VAR without quotes → warning
8. AST analysis (Python): import os, subprocess, pickle, eval(), exec()
9. Allowlist: unknown bioinformatics tool → warning
10. Best practices: missing set -euo pipefail, missing shebang, missing header

### Key invariant
Safety is deterministic Python code, not an LLM instruction.
A jailbroken LLM can generate anything, but safety.py will block it
regardless of what the LLM "thinks" or "believes".

---

## Plugin System

Plugins are separate git repos installed to ~/.biopipe/plugins/<name>.
Each plugin has manifest.json declaring tools, hooks, and permissions.
Core has ZERO built-in domain tools — all bioinformatics comes from plugins.

Plugin lifecycle:
1. git clone <repo> ~/.biopipe/plugins/<name>
2. PluginLoader.discover() scans manifests
3. _validate_manifest() checks forbidden capabilities
4. importlib.import_module(entry_point) — entry_point must start with "biopipe_"
5. _validate_tool() checks permission ≤ GENERATE
6. Tool registered in ToolRegistry
7. All plugin output passes through same 10-layer SafetyValidator as core

Forbidden plugin capabilities: execute, network, write_system, modify_core,
escalate_permission, disable_safety, access_env, raw_llm.

---

## What this project is NOT

- NOT a web application (no HTTP server, no REST API, no frontend)
- NOT a cloud service (everything runs locally, zero telemetry)
- NOT a medical device (generates scripts, doesn't process patient data)
- NOT an autonomous executor (dry-run by default, user must review and run)
- NOT a replacement for bioinformatics knowledge (assistant, not autopilot)

---

## Tech Stack

- Language: Python 3.10+
- CLI: Typer
- LLM: llama.cpp (embedded via llama-cpp-python) or Ollama (localhost)
- RAG: ChromaDB (local vector database)
- Models: GGUF files (Qwen 2.5 Coder, Llama 3.3, Mistral)
- Tests: pytest (185 tests, all passing)
- No external API calls during operation (only during model download)

---

## File Statistics (v0.4.0)

- 44 Python source files
- 4609 lines of source code
- 1558 lines of tests
- 1162 lines of documentation
- 30 core modules
- 185 tests, all passing
- 0 domain-specific code in core (all via plugins)

---

## When reviewing this code, pay attention to:

1. **Safety invariants** — can any code path bypass the 10-layer SafetyValidator?
2. **Immutability** — can any runtime code mutate Config, PermissionPolicy, or allowlist?
3. **Plugin isolation** — can a plugin access runtime internals (_config, _safety, _session)?
4. **Session integrity** — can restore() load injected SYSTEM messages?
5. **LLM independence** — does any security decision depend on LLM output? (should be: never)
6. **Zero network** — does any code make outbound HTTP calls during operation? (should be: never)
7. **Separation** — does core/ import from generators/, plugins/, or external packages? (should be: only from core/ and stdlib)
