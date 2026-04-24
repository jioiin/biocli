"""Tests for LLM, RAG chunker, and runtime (no generators — those are plugins)."""

import asyncio
import pytest
from biopipe.llm.base import MockLLM
from biopipe.rag.chunker import chunk_manpage, chunk_plain_text
from biopipe.core.config import Config
from biopipe.core.runtime import AgentRuntime


# === MockLLM Tests ===

class TestMockLLM:
    def test_generate_returns_message(self) -> None:
        llm = MockLLM(response="hello")
        msg = asyncio.run(llm.generate([], []))
        assert msg.content == "hello"
        assert msg.role.value == "assistant"

    def test_health_check(self) -> None:
        llm = MockLLM()
        assert asyncio.run(llm.health_check()) is True

    def test_model_id(self) -> None:
        llm = MockLLM()
        assert llm.model_id() == "mock-llm-v1"


# === Chunker Tests ===

class TestChunker:
    def test_manpage_sections(self) -> None:
        text = """NAME
    samtools - utilities for SAM/BAM files

SYNOPSIS
    samtools sort [-n] [-o out.bam] in.bam

DESCRIPTION
    Samtools is a set of utilities.

OPTIONS
    -n    Sort by read name
    -o    Output file
"""
        chunks = chunk_manpage(text, "samtools")
        assert len(chunks) >= 3
        assert all(c.tool_name == "samtools" for c in chunks)
        sections = {c.section for c in chunks}
        assert "NAME" in sections
        assert "OPTIONS" in sections

    def test_empty_text(self) -> None:
        chunks = chunk_manpage("", "empty")
        assert len(chunks) == 1  # FULL section

    def test_plain_text_chunking(self) -> None:
        text = "\n\n".join([f"Paragraph {i} with some content." for i in range(20)])
        chunks = chunk_plain_text(text, "tool", max_chunk_size=200)
        assert len(chunks) > 1
        assert all(c.char_count <= 250 for c in chunks)

    def test_chunk_has_metadata(self) -> None:
        chunks = chunk_manpage("OPTIONS\n  -t threads", "bwa")
        assert chunks[0].tool_name == "bwa"
        assert chunks[0].char_count > 0


# === Runtime Integration Test ===

class TestRuntimeIntegration:
    def test_runtime_creates_with_mock(self) -> None:
        config = Config.load()
        llm = MockLLM(response="safe output")
        runtime = AgentRuntime(config, llm)
        assert runtime is not None

    def test_health_check_with_mock(self) -> None:
        config = Config.load()
        llm = MockLLM()
        runtime = AgentRuntime(config, llm)
        checks = asyncio.run(runtime.health_check())
        assert checks["llm"] is True

    def test_no_tools_by_default(self) -> None:
        """Core has ZERO built-in tools. All come from plugins."""
        config = Config.load()
        llm = MockLLM()
        runtime = AgentRuntime(config, llm)
        assert runtime._registry.names() == []
