from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import Any

from ..models.course import CourseBlock, CourseDocument
from .chunker import Chunker
from .cleaner import TextCleaner
from .processor import ChunkProcessor

_LAYOUT_NAME_RE = re.compile(
    r"^(?:"
    r"Title|Subtitle|Picture|Content Placeholder|Text Placeholder|"
    r"ContentPlaceholder|TextBox|Text Box|Object|Table|Chart|Diagram"
    r")\s+\d+$",
    flags=re.IGNORECASE,
)


class Pipeline:
    def __init__(
        self,
        cleaner: TextCleaner | None = None,
        chunker: Chunker | None = None,
        processor: ChunkProcessor | None = None,
    ) -> None:
        self.cleaner = cleaner or TextCleaner()
        self.chunker = chunker or Chunker()
        self.processor = processor or ChunkProcessor()

    def run(self, parsed_document: dict, *, source_file: str = "unknown") -> dict:
        text = self._extract_text(parsed_document)
        cleaned = self.cleaner.clean(text)
        chunks = self.chunker.chunk(cleaned, source=source_file)

        blocks: list[CourseBlock] = []
        for chunk in chunks:
            analysis = self.processor.process(chunk.text)
            block_type = str(analysis.get("block_type") or "theory")
            paragraphs = self._as_string_list(analysis.get("paragraphs")) or [chunk.text]
            blocks.append(
                CourseBlock(
                    index=chunk.index,
                    block_type=block_type,
                    title=str(
                        analysis.get("title")
                        or self._title_for_block(block_type, chunk.index)
                    ),
                    content="\n\n".join(paragraphs),
                    lead=str(analysis.get("lead") or ""),
                    paragraphs=paragraphs,
                    summary=str(analysis.get("summary") or ""),
                    key_terms=self._as_string_list(analysis.get("key_terms")),
                    takeaways=self._as_string_list(analysis.get("takeaways")),
                    hints=self._as_string_list(analysis.get("hints")),
                    metadata={"source": chunk.source, "source_kind": "text"},
                )
            )

        table_blocks = self._build_table_blocks(
            parsed_document,
            start_index=len(blocks) + 1,
            source=source_file,
        )
        blocks.extend(table_blocks)

        image_blocks = self._build_image_blocks(
            parsed_document,
            start_index=len(blocks) + 1,
            source=source_file,
        )
        blocks.extend(image_blocks)

        quiz_block = self._build_quiz_block(blocks, start_index=len(blocks) + 1, source=source_file)
        if quiz_block is not None:
            blocks.append(quiz_block)

        course = CourseDocument(
            title=self._title_from_document(parsed_document, source_file),
            source_file=source_file,
            blocks=blocks,
            metadata={
                "source_file_type": parsed_document.get("file_type"),
                "text_chunk_count": len(chunks),
                "table_count": len(table_blocks),
                "image_count": len(image_blocks),
                "quiz_count": 1 if quiz_block is not None else 0,
                "block_count": len(blocks),
            },
        )
        return self._serialize(course)

    def _extract_text(self, parsed_document: dict) -> str:
        if "content" in parsed_document and isinstance(parsed_document["content"], str):
            return parsed_document["content"]

        parts: list[str] = []
        for key in ("blocks", "paragraphs", "pages", "slides"):
            value = parsed_document.get(key)
            if not isinstance(value, list):
                continue
            parts.extend(self._collect_text_items(value))
        return "\n\n".join(self._dedupe_text_parts(parts))

    def _collect_text_items(self, items: Iterable[dict]) -> list[str]:
        collected: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue

            for field in ("text", "summary", "content"):
                value = item.get(field)
                self._append_clean_text(collected, value)

            notes = item.get("notes")
            if isinstance(notes, str) and notes.strip():
                self._append_clean_text(collected, notes)
            elif isinstance(notes, dict):
                collected.extend(self._flatten_nested_text(notes))

            for nested in ("figures", "images", "shapes"):
                nested_value = item.get(nested)
                if isinstance(nested_value, list):
                    collected.extend(self._flatten_nested_text(nested_value))
        return collected

    def _dedupe_text_parts(self, parts: list[str]) -> list[str]:
        kept: list[str] = []
        normalized_kept: list[str] = []

        for part in parts:
            normalized = self._normalize_for_dedupe(part)
            if not normalized:
                continue
            if any(
                normalized == existing
                or (len(normalized) > 40 and normalized in existing)
                for existing in normalized_kept
            ):
                continue

            keep_indexes = [
                index
                for index, existing in enumerate(normalized_kept)
                if not (len(existing) > 40 and existing in normalized)
            ]
            kept = [kept[index] for index in keep_indexes]
            normalized_kept = [normalized_kept[index] for index in keep_indexes]
            kept.append(part)
            normalized_kept.append(normalized)

        return kept

    def _normalize_for_dedupe(self, value: str) -> str:
        value = re.sub(r"\s+", " ", value).strip().lower()
        value = re.sub(
            r"\b(?:title|subtitle|picture|content placeholder|text placeholder|"
            r"contentplaceholder|textbox|text box|object|table|chart|diagram)\s+\d+\b",
            "",
            value,
        )
        return re.sub(r"\s+", " ", value).strip()

    def _flatten_nested_text(self, value: Any) -> list[str]:
        collected: list[str] = []
        if isinstance(value, str) and value.strip():
            return [value]
        if isinstance(value, list):
            for item in value:
                collected.extend(self._flatten_nested_text(item))
            return collected
        if isinstance(value, dict):
            for field in ("text", "caption", "caption_hint"):
                text = value.get(field)
                self._append_clean_text(collected, text)
            for key, nested in value.items():
                if key == "rows":
                    continue
                if isinstance(nested, (list, dict)):
                    collected.extend(self._flatten_nested_text(nested))
        return collected

    def _append_clean_text(self, collected: list[str], value: Any) -> None:
        if not isinstance(value, str):
            return

        text = value.strip()
        if not text or self._is_layout_name(text):
            return
        collected.append(text)

    def _is_layout_name(self, value: str | None) -> bool:
        if not isinstance(value, str):
            return False
        return bool(_LAYOUT_NAME_RE.match(value.strip()))

    def _build_table_blocks(
        self,
        parsed_document: dict,
        *,
        start_index: int,
        source: str,
    ) -> list[CourseBlock]:
        tables = self._extract_tables(parsed_document)
        blocks: list[CourseBlock] = []

        for offset, table in enumerate(tables):
            rows = table["rows"]
            headers, body_rows = self._split_table(rows)
            caption = table.get("caption") or f"Таблица {offset + 1}"
            summary = self._summarize_table(headers, body_rows)
            blocks.append(
                CourseBlock(
                    index=start_index + offset,
                    block_type="table",
                    title=str(caption),
                    content=summary,
                    lead="Структурированные данные из исходной лекции.",
                    paragraphs=[summary],
                    summary=summary,
                    key_terms=[],
                    takeaways=[],
                    hints=["Используй таблицу для сравнения значений, этапов или признаков."],
                    metadata={
                        "source": source,
                        "source_kind": "table",
                        "table": {
                            "headers": headers,
                            "rows": body_rows,
                        },
                        **table.get("metadata", {}),
                    },
                )
            )

        return blocks

    def _extract_tables(self, parsed_document: dict) -> list[dict]:
        tables: list[dict] = []
        seen: set[str] = set()

        def visit(value: Any, context: dict[str, Any]) -> None:
            if isinstance(value, list):
                for item in value:
                    visit(item, context)
                return

            if not isinstance(value, dict):
                return

            next_context = dict(context)
            for key in ("slide_number", "page_number", "table_number", "shape_index", "name"):
                if key in value:
                    next_context[key] = value[key]

            rows = value.get("rows")
            if self._looks_like_table(rows):
                normalized_rows = self._normalize_table_rows(rows)
                table_key = json.dumps(normalized_rows, ensure_ascii=False)
                if table_key not in seen:
                    seen.add(table_key)
                    caption = self._table_caption(value, next_context, len(tables) + 1)
                    tables.append(
                        {
                            "caption": caption,
                            "rows": normalized_rows,
                            "metadata": next_context,
                        }
                    )

            for key in ("blocks", "tables", "slides", "pages", "shapes"):
                nested = value.get(key)
                if isinstance(nested, list):
                    visit(nested, next_context)

        visit(parsed_document, {})
        return tables

    def _build_image_blocks(
        self,
        parsed_document: dict,
        *,
        start_index: int,
        source: str,
    ) -> list[CourseBlock]:
        images = self._extract_images(parsed_document)
        blocks: list[CourseBlock] = []

        for offset, image in enumerate(images):
            image_summary = self._describe_image(image)
            blocks.append(
                CourseBlock(
                    index=start_index + offset,
                    block_type="image",
                    title=f"Иллюстрация {offset + 1}",
                    content=image_summary,
                    lead="Визуальный материал из исходной лекции.",
                    paragraphs=[image_summary],
                    summary=image_summary,
                    key_terms=[],
                    takeaways=[],
                    hints=[
                        "Этот блок стоит поставить рядом с разделом, где объясняется соответствующее понятие.",
                        "Для точного описания изображения позже можно подключить OCR или vision-модель.",
                    ],
                    metadata={
                        "source": source,
                        "source_kind": "image",
                        "media_type": "image",
                        **image,
                    },
                )
            )

        return blocks

    def _build_quiz_block(
        self,
        blocks: list[CourseBlock],
        *,
        start_index: int,
        source: str,
    ) -> CourseBlock | None:
        sections = [
            {
                "index": block.index,
                "type": block.block_type,
                "title": block.title,
                "lead": block.lead,
                "summary": block.summary,
                "key_terms": block.key_terms,
                "takeaways": block.takeaways,
            }
            for block in blocks
            if block.block_type not in {"image", "quiz"}
        ]
        quiz = self.processor.build_quiz(sections, max_questions=5)
        questions = quiz.get("questions")
        if not isinstance(questions, list) or not questions:
            return None

        return CourseBlock(
            index=start_index,
            block_type="quiz",
            title="Мини-квиз",
            content="Проверь, насколько хорошо ты понял ключевые идеи лонгрида.",
            lead="Короткая проверка по главным понятиям и выводам материала.",
            paragraphs=["Выбери один правильный ответ в каждом вопросе."],
            summary=f"Квиз из {len(questions)} вопросов с multiple-choice ответами.",
            key_terms=[],
            takeaways=[],
            hints=["После выбора ответа можно свериться с объяснением."],
            metadata={
                "source": source,
                "source_kind": "quiz",
                "quiz": {
                    "questions": questions,
                },
            },
        )

    def _extract_images(self, parsed_document: dict) -> list[dict]:
        images: list[dict] = []
        seen: set[str] = set()

        def visit(value: Any, context: dict[str, Any]) -> None:
            if isinstance(value, list):
                for item in value:
                    visit(item, context)
                return

            if not isinstance(value, dict):
                return

            next_context = dict(context)
            for key in ("slide_number", "page_number", "figure_number", "image_number", "name"):
                if key in value:
                    next_context[key] = value[key]

            image_path = value.get("image_path")
            if isinstance(image_path, str) and image_path.strip():
                image_key = image_path.strip()
                if image_key not in seen:
                    seen.add(image_key)
                    image_data = {
                        **next_context,
                        "image_path": image_key,
                        "caption": self._meaningful_text(value.get("caption") or value.get("caption_hint")),
                        "name": self._meaningful_text(value.get("name"))
                        or self._meaningful_text(value.get("filename")),
                        "content_type": value.get("content_type"),
                    }
                    images.append(image_data)

            for key in ("blocks", "paragraphs", "figures", "images", "slides", "pages", "shapes"):
                nested = value.get(key)
                if isinstance(nested, list):
                    visit(nested, next_context)

        visit(parsed_document, {})
        return images

    def _meaningful_text(self, value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        text = value.strip()
        if not text or self._is_layout_name(text):
            return None
        return text

    def _describe_image(self, image: dict) -> str:
        caption = image.get("caption")
        name = image.get("name")
        location = self._image_location(image)
        if isinstance(caption, str) and caption.strip():
            return f"{location} изображение с подписью: {caption.strip()}."
        if isinstance(name, str) and name.strip():
            return f"{location} изображение: {name.strip()}."
        return f"{location} изображение без текстовой подписи."

    def _image_location(self, image: dict) -> str:
        if image.get("slide_number"):
            return f"На слайде {image['slide_number']}"
        if image.get("page_number"):
            return f"На странице {image['page_number']}"
        return "В материале"

    def _title_from_document(self, parsed_document: dict, source_file: str) -> str:
        filename = parsed_document.get("filename") or source_file
        return str(filename).rsplit(".", 1)[0]

    def _title_for_block(self, block_type: str, index: int) -> str:
        mapping = {
            "introduction": "Введение",
            "theory": "Теория",
            "examples": "Примеры",
            "conclusion": "Заключение",
            "table": "Таблица",
            "image": "Иллюстрация",
            "quiz": "Мини-квиз",
        }
        return f"{mapping.get(block_type, 'Блок')} {index}"

    def _split_table(self, rows: list[list[str]]) -> tuple[list[str], list[list[str]]]:
        if not rows:
            return [], []
        if len(rows) == 1:
            return [f"Колонка {index + 1}" for index in range(len(rows[0]))], rows
        return rows[0], rows[1:]

    def _summarize_table(self, headers: list[str], rows: list[list[str]]) -> str:
        column_count = len(headers) if headers else max((len(row) for row in rows), default=0)
        row_count = len(rows)
        return f"Таблица содержит {row_count} строк и {column_count} столбцов."

    def _looks_like_table(self, rows: Any) -> bool:
        return isinstance(rows, list) and any(isinstance(row, list) for row in rows)

    def _normalize_table_rows(self, rows: Any) -> list[list[str]]:
        normalized: list[list[str]] = []
        if not isinstance(rows, list):
            return normalized
        for row in rows:
            if isinstance(row, list):
                normalized.append([str(cell).strip() for cell in row])
        return [row for row in normalized if any(cell for cell in row)]

    def _table_caption(self, value: dict, context: dict[str, Any], index: int) -> str:
        name = self._meaningful_text(value.get("name"))
        if name:
            return name
        if context.get("slide_number"):
            return f"Таблица {index} со слайда {context['slide_number']}"
        if context.get("page_number"):
            return f"Таблица {index} со страницы {context['page_number']}"
        return f"Таблица {index}"

    def _as_string_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if str(item).strip()]

    def _serialize(self, course: CourseDocument) -> dict:
        return {
            "title": course.title,
            "source_file": course.source_file,
            "metadata": course.metadata,
            "blocks": [
                {
                    "index": block.index,
                    "type": block.block_type,
                    "title": block.title,
                    "content": block.content,
                    "lead": block.lead,
                    "paragraphs": block.paragraphs,
                    "summary": block.summary,
                    "key_terms": block.key_terms,
                    "takeaways": block.takeaways,
                    "hints": block.hints,
                    "metadata": block.metadata,
                    "table": block.metadata.get("table"),
                    "quiz": block.metadata.get("quiz"),
                    "image_path": block.metadata.get("image_path"),
                    "media_type": block.metadata.get("media_type"),
                }
                for block in course.blocks
            ],
        }
