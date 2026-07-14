from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChunkAnalysis:
    block_type: str
    summary: str
    key_terms: list[str] = field(default_factory=list)
    hints: list[str] = field(default_factory=list)
    source_excerpt: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CourseBlock:
    index: int
    block_type: str
    title: str
    content: str
    summary: str
    lead: str = ""
    paragraphs: list[str] = field(default_factory=list)
    takeaways: list[str] = field(default_factory=list)
    key_terms: list[str] = field(default_factory=list)
    hints: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CourseDocument:
    title: str
    source_file: str
    blocks: list[CourseBlock] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
