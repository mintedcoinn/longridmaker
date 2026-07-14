from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TextChunk:
    index: int
    text: str
    source: str | None = None


class Chunker:
    def __init__(self, max_chars: int = 2200) -> None:
        self.max_chars = max_chars

    def chunk(self, text: str, source: str | None = None) -> list[TextChunk]:
        paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
        chunks: list[TextChunk] = []
        current: list[str] = []
        current_len = 0

        for paragraph in paragraphs:
            paragraph_len = len(paragraph)
            if current and current_len + paragraph_len + 2 > self.max_chars:
                chunks.append(
                    TextChunk(index=len(chunks) + 1, text="\n\n".join(current), source=source)
                )
                current = []
                current_len = 0

            current.append(paragraph)
            current_len += paragraph_len + 2

        if current:
            chunks.append(TextChunk(index=len(chunks) + 1, text="\n\n".join(current), source=source))

        return chunks or [TextChunk(index=1, text=text, source=source)]
