"""
Shared chunking utilities for Clawdiney.

This module provides text chunking strategies used by both the indexer
and query engine for consistent text segmentation.
"""
import re
from typing import TypedDict

from config import Config


class Chunk(TypedDict):
    """Represents a text chunk with header and content."""

    header: str
    content: str


def fixed_size_chunking(
    text: str, chunk_size: int = 500, overlap: int = 50
) -> list[Chunk]:
    """
    Split text into fixed-size chunks with overlap.

    Args:
        text: Input text to chunk
        chunk_size: Target chunk size in characters (default: 500)
        overlap: Number of overlapping characters between chunks (default: 50)

    Returns:
        List of dicts with 'header' and 'content' keys
    """
    chunks: list[Chunk] = []
    start = 0

    while start < len(text):
        end = start + chunk_size
        chunk_text = text[start:end]
        chunks.append({"header": "Fixed Size", "content": chunk_text.strip()})
        start = end - overlap if overlap < chunk_size else end

    return [chunk for chunk in chunks if chunk["content"]]


def semantic_chunking(text: str, chunk_size: int | None = None) -> list[Chunk]:
    """
    Split text at sentence boundaries, grouping into target-size chunks.

    Args:
        text: Input text to chunk
        chunk_size: Target chunk size in characters (default: Config.CHUNK_SIZE)

    Returns:
        List of dicts with 'header' and 'content' keys
    """
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: list[Chunk] = []
    current_chunk = ""
    target_size = chunk_size or Config.CHUNK_SIZE

    for sentence in sentences:
        if len(current_chunk) + len(sentence) > target_size and current_chunk:
            chunks.append({"header": "Semantic", "content": current_chunk.strip()})
            current_chunk = sentence
        else:
            current_chunk = f"{current_chunk} {sentence}".strip()

    if current_chunk:
        chunks.append({"header": "Semantic", "content": current_chunk.strip()})

    return chunks


def markdown_chunking(text: str) -> list[Chunk]:
    """
    Split text by markdown headers (# Header).

    Args:
        text: Markdown text to chunk

    Returns:
        List of dicts with 'header' and 'content' keys
    """
    chunks: list[Chunk] = []
    current_header = "Root"
    current_lines: list[str] = []

    for line in text.splitlines():
        if re.match(r"^#+\s", line):
            if current_lines:
                chunks.append({
                    "header": current_header,
                    "content": "\n".join(current_lines).strip(),
                })
            current_header = line.lstrip("#").strip() or "Root"
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        chunks.append({
            "header": current_header,
            "content": "\n".join(current_lines).strip(),
        })

    if not chunks and text.strip():
        chunks.append({"header": "Root", "content": text.strip()})

    return [chunk for chunk in chunks if chunk["content"] or chunk["header"] != "Root"]


def chunk_text(
    text: str,
    strategy: str | None = None,
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> list[Chunk]:
    """
    Split text using the configured strategy.

    Args:
        text: Input text to chunk
        strategy: Chunking strategy - 'headers', 'fixed', or 'semantic'
                  (default: Config.CHUNKING_STRATEGY)
        chunk_size: Target chunk size (default: Config.CHUNK_SIZE)
        overlap: Overlap size for fixed chunking (default: Config.CHUNK_OVERLAP)

    Returns:
        List of dicts with 'header' and 'content' keys
    """
    strategy = strategy or Config.CHUNKING_STRATEGY
    chunk_size = chunk_size or Config.CHUNK_SIZE
    overlap = overlap if overlap is not None else Config.CHUNK_OVERLAP

    if strategy == "headers":
        return markdown_chunking(text)
    if strategy == "fixed":
        return fixed_size_chunking(text, chunk_size, overlap)
    if strategy == "semantic":
        return semantic_chunking(text, chunk_size)
    return markdown_chunking(text)
