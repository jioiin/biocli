"""RAG retriever: hybrid search over indexed bioinformatics docs."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RetrievedChunk:
    """Single retrieved document chunk with relevance score."""
    content: str
    tool_name: str
    section: str
    score: float


class RAGRetriever:
    """Retrieve relevant documentation chunks from ChromaDB.

    Uses ChromaDB's built-in embedding + cosine similarity.
    Requires: pip install chromadb
    """

    def __init__(self, db_path: str = "~/.local/share/biopipe/chromadb") -> None:
        try:
            import chromadb
        except ImportError:
            raise ImportError(
                "chromadb is required for RAG. Install: pip install chromadb"
            )

        from pathlib import Path
        resolved = Path(db_path).expanduser()
        self._client = chromadb.PersistentClient(path=str(resolved))
        self._collection = self._client.get_or_create_collection(
            name="biopipe_docs",
            metadata={"hnsw:space": "cosine"},
        )

    def search(
        self,
        query: str,
        top_k: int = 5,
        tool_filter: str | None = None,
    ) -> list[RetrievedChunk]:
        """Search for relevant documentation chunks.

        Args:
            query: Natural language query.
            top_k: Number of results to return.
            tool_filter: Optional tool name to filter by (e.g., 'bwa').

        Returns:
            List of RetrievedChunk sorted by relevance.
        """
        where = {"tool": tool_filter} if tool_filter else None

        results = self._collection.query(
            query_texts=[query],
            n_results=top_k,
            where=where,
        )

        chunks: list[RetrievedChunk] = []
        if not results["documents"] or not results["documents"][0]:
            return chunks

        docs = results["documents"][0]
        metas = results["metadatas"][0] if results["metadatas"] else [{}] * len(docs)
        dists = results["distances"][0] if results["distances"] else [0.0] * len(docs)

        for doc, meta, dist in zip(docs, metas, dists):
            chunks.append(RetrievedChunk(
                content=doc,
                tool_name=meta.get("tool", "unknown"),
                section=meta.get("section", "unknown"),
                score=1.0 - dist,  # cosine distance → similarity
            ))

        return chunks

    def format_context(self, chunks: list[RetrievedChunk]) -> str:
        """Format retrieved chunks as context string for LLM prompt.

        Args:
            chunks: Retrieved chunks from search().

        Returns:
            Formatted string for injection into LLM context.
        """
        if not chunks:
            return ""

        parts: list[str] = []
        for c in chunks:
            parts.append(
                f"--- {c.tool_name} ({c.section}) [relevance: {c.score:.2f}] ---\n"
                f"{c.content}\n"
            )

        return "\n".join(parts)

    def is_empty(self) -> bool:
        """Check if the index has any documents."""
        return self._collection.count() == 0
