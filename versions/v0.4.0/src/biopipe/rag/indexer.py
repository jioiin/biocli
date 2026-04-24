"""Index bioinformatics tool documentation into ChromaDB."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .chunker import Chunk, chunk_manpage, chunk_plain_text


class RAGIndexer:
    """Index man pages and docs into ChromaDB vector store.

    Requires: pip install chromadb
    """

    def __init__(self, db_path: str = "~/.local/share/biopipe/chromadb") -> None:
        try:
            import chromadb
        except ImportError:
            raise ImportError(
                "chromadb is required for RAG. Install: pip install chromadb"
            )

        resolved = Path(db_path).expanduser()
        resolved.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(resolved))
        self._collection = self._client.get_or_create_collection(
            name="biopipe_docs",
            metadata={"hnsw:space": "cosine"},
        )

    def index_manpage(self, tool_name: str) -> int:
        """Capture man page for a tool and index its chunks.

        Args:
            tool_name: Name of the tool (e.g., 'fastqc', 'samtools').

        Returns:
            Number of chunks indexed.
        """
        text = self._capture_man(tool_name)
        if not text:
            return 0

        chunks = chunk_manpage(text, tool_name)
        self._store_chunks(chunks)
        return len(chunks)

    def index_file(self, path: str, tool_name: str) -> int:
        """Index a plain text documentation file.

        Args:
            path: Path to the documentation file.
            tool_name: Name of the tool this doc belongs to.

        Returns:
            Number of chunks indexed.
        """
        text = Path(path).read_text(encoding="utf-8", errors="replace")
        chunks = chunk_plain_text(text, tool_name)
        self._store_chunks(chunks)
        return len(chunks)

    def index_help(self, tool_name: str) -> int:
        """Capture --help output and index it.

        Args:
            tool_name: Name of the tool.

        Returns:
            Number of chunks indexed.
        """
        text = self._capture_help(tool_name)
        if not text:
            return 0

        chunks = chunk_plain_text(text, tool_name)
        self._store_chunks(chunks)
        return len(chunks)

    def stats(self) -> dict[str, int]:
        """Return collection statistics."""
        return {"total_chunks": self._collection.count()}

    def _store_chunks(self, chunks: list[Chunk]) -> None:
        """Store chunks in ChromaDB with metadata."""
        if not chunks:
            return

        ids = [f"{c.tool_name}_{c.section}_{i}" for i, c in enumerate(chunks)]
        documents = [c.content for c in chunks]
        metadatas = [
            {"tool": c.tool_name, "section": c.section, "chars": c.char_count}
            for c in chunks
        ]

        self._collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )

    @staticmethod
    def _capture_man(tool_name: str) -> str:
        """Capture man page text. Returns empty string if not found."""
        try:
            result = subprocess.run(
                ["man", tool_name],
                capture_output=True,
                text=True,
                timeout=10,
                env={"MANPAGER": "cat", "COLUMNS": "120", "PATH": "/usr/bin:/usr/local/bin"},
            )
            return result.stdout if result.returncode == 0 else ""
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return ""

    @staticmethod
    def _capture_help(tool_name: str) -> str:
        """Capture --help output."""
        try:
            result = subprocess.run(
                [tool_name, "--help"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.stdout or result.stderr
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return ""
