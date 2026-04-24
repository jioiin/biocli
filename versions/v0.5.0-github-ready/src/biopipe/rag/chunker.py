"""Semantic chunker for bioinformatics tool documentation.

Splits man pages and docs by sections (SYNOPSIS, OPTIONS, EXAMPLES)
rather than fixed character count.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Chunk:
    """Single chunk of documentation."""
    tool_name: str
    section: str
    content: str
    char_count: int


# Common man-page section headers
_SECTION_PATTERN = re.compile(
    r"^(SYNOPSIS|NAME|DESCRIPTION|OPTIONS|EXAMPLES?|USAGE|"
    r"COMMANDS?|SEE ALSO|BUGS|AUTHORS?|EXIT STATUS|"
    r"RETURN VALUES?|ENVIRONMENT|FILES|NOTES?|"
    r"COMPATIBILITY|HISTORY|STANDARDS)",
    re.MULTILINE | re.IGNORECASE,
)


def chunk_manpage(text: str, tool_name: str, max_chunk_size: int = 2000) -> list[Chunk]:
    """Split a man page into semantic chunks by section.

    Args:
        text: Raw man page text.
        tool_name: Name of the tool (e.g., 'fastqc', 'bwa').
        max_chunk_size: Max characters per chunk. Sections larger than this
                        are split at paragraph boundaries.

    Returns:
        List of Chunk objects.
    """
    sections = _split_sections(text)
    chunks: list[Chunk] = []

    for section_name, section_text in sections:
        if len(section_text) <= max_chunk_size:
            chunks.append(Chunk(
                tool_name=tool_name,
                section=section_name,
                content=section_text.strip(),
                char_count=len(section_text),
            ))
        else:
            sub_chunks = _split_at_paragraphs(section_text, max_chunk_size)
            for i, sub in enumerate(sub_chunks):
                chunks.append(Chunk(
                    tool_name=tool_name,
                    section=f"{section_name}_part{i + 1}",
                    content=sub.strip(),
                    char_count=len(sub),
                ))

    return chunks


def chunk_plain_text(text: str, tool_name: str, max_chunk_size: int = 1500) -> list[Chunk]:
    """Chunk plain text docs (README, help output) by paragraphs.

    Args:
        text: Plain text documentation.
        tool_name: Name of the tool.
        max_chunk_size: Max characters per chunk.

    Returns:
        List of Chunk objects.
    """
    paragraphs = text.split("\n\n")
    chunks: list[Chunk] = []
    current = ""

    for para in paragraphs:
        if len(current) + len(para) + 2 > max_chunk_size and current:
            chunks.append(Chunk(
                tool_name=tool_name,
                section="text",
                content=current.strip(),
                char_count=len(current),
            ))
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para

    if current.strip():
        chunks.append(Chunk(
            tool_name=tool_name,
            section="text",
            content=current.strip(),
            char_count=len(current),
        ))

    return chunks


def _split_sections(text: str) -> list[tuple[str, str]]:
    """Split text into (section_name, section_body) pairs."""
    matches = list(_SECTION_PATTERN.finditer(text))

    if not matches:
        return [("FULL", text)]

    sections: list[tuple[str, str]] = []

    if matches[0].start() > 0:
        sections.append(("HEADER", text[: matches[0].start()]))

    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections.append((match.group(0).upper(), text[start:end]))

    return sections


def _split_at_paragraphs(text: str, max_size: int) -> list[str]:
    """Split text at double-newlines respecting max_size."""
    paragraphs = text.split("\n\n")
    result: list[str] = []
    current = ""

    for para in paragraphs:
        if len(current) + len(para) + 2 > max_size and current:
            result.append(current)
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para

    if current:
        result.append(current)

    return result
