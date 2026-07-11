from __future__ import annotations

import mimetypes
import re
import tempfile
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

_HEADING_STYLE_RE = re.compile(r"^Heading\s*(\d+)$", re.IGNORECASE)
_LIST_STYLE_RE = re.compile(
    r"^(?:List\s+)?(?:Bullet|Number|Paragraph)\s*(\d+)?$",
    re.IGNORECASE,
)


def parse_docx(file_path: Path, assets_dir: Path | None = None) -> dict:
    """Parse a DOCX file and return structured JSON."""
    doc = Document(str(file_path))
    resolved_assets_dir = _resolve_assets_dir(assets_dir)

    paragraphs: list[dict] = []
    tables: list[dict] = []
    figures: list[dict] = []
    blocks: list[dict] = []

    table_number = 0
    figure_number = 0

    for block in _iter_block_items(doc):
        if isinstance(block, Paragraph):
            paragraph_data, new_figures, figure_number = _parse_paragraph(
                block, resolved_assets_dir, figure_number
            )
            if paragraph_data is not None:
                paragraphs.append(paragraph_data)
                blocks.append(paragraph_data)
            if new_figures:
                figures.extend(new_figures)

        elif isinstance(block, Table):
            table_number += 1
            table_data = {
                "type": "table",
                "table_number": table_number,
                "rows": _extract_table_rows(block),
            }
            tables.append(table_data)
            blocks.append(table_data)

    return {
        "file_type": "docx",
        "blocks": blocks,
        "paragraphs": paragraphs,
        "tables": tables,
        "figures": figures,
        "metadata": {
            "total_blocks": len(blocks),
            "total_paragraphs": len(paragraphs),
            "total_tables": len(tables),
            "total_figures": len(figures),
            "assets_dir": str(resolved_assets_dir),
        },
    }


def _resolve_assets_dir(assets_dir: Path | None) -> Path:
    if assets_dir is not None:
        assets_dir.mkdir(parents=True, exist_ok=True)
        return assets_dir

    return Path(tempfile.mkdtemp(prefix="file-parser-docx-assets-"))


def _iter_block_items(document):
    for child in document.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, document)
        elif child.tag == qn("w:tbl"):
            yield Table(child, document)


def _parse_paragraph(
    paragraph: Paragraph, assets_dir: Path, figure_number: int
) -> tuple[dict | None, list[dict], int]:
    text = paragraph.text.strip()
    style = paragraph.style
    style_name = style.name if style else "Normal"
    style_id = style.style_id if style else None

    heading_level = _heading_level(style_name, style_id)
    list_info = _list_info(paragraph, style_name, style_id)
    figures, figure_number = _extract_figures(paragraph, assets_dir, figure_number)

    if not text and not figures:
        return None, [], figure_number

    paragraph_data = {
        "type": "heading"
        if heading_level is not None
        else "list_item"
        if list_info is not None
        else "paragraph",
        "text": text,
        "style": style_name,
        "style_id": style_id,
        "heading_level": heading_level,
        "is_list": list_info is not None,
        "list_level": list_info["list_level"] if list_info else None,
        "list_numbering_id": list_info["list_numbering_id"] if list_info else None,
        "list_type": list_info["list_type"] if list_info else None,
        "figures": figures,
    }

    return paragraph_data, figures, figure_number


def _heading_level(style_name: str | None, style_id: str | None) -> int | None:
    for candidate in (style_id, style_name):
        if not candidate:
            continue
        candidate = candidate.replace("_", " ")
        match = _HEADING_STYLE_RE.match(candidate)
        if match:
            return int(match.group(1))
        match = re.match(r"^Heading(\d+)$", candidate, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def _list_info(
    paragraph: Paragraph, style_name: str | None, style_id: str | None
) -> dict | None:
    numbering = None

    p_pr = paragraph._p.pPr
    if p_pr is not None and p_pr.numPr is not None:
        num_pr = p_pr.numPr
        list_level = _xml_int(getattr(num_pr, "ilvl", None), default=0) + 1
        numbering = {
            "list_level": list_level,
            "list_numbering_id": _xml_int(getattr(num_pr, "numId", None)),
            "list_type": _guess_list_type(style_name, style_id),
        }
        return numbering

    for candidate in (style_id, style_name):
        if not candidate:
            continue

        style_token = candidate.replace("_", " ")
        style_token = (
            style_token.replace("ListBullet", "List Bullet ")
            .replace("ListNumber", "List Number ")
            .replace("ListParagraph", "List Paragraph ")
        )
        if _LIST_STYLE_RE.match(style_token):
            list_level = 1
            level_match = re.search(r"(\d+)$", style_token)
            if level_match:
                list_level = int(level_match.group(1))
            numbering = {
                "list_level": list_level,
                "list_numbering_id": None,
                "list_type": _guess_list_type(style_name, style_id),
            }
            break

    return numbering


def _guess_list_type(style_name: str | None, style_id: str | None) -> str | None:
    style_token = f"{style_id or ''} {style_name or ''}".lower()
    if "bullet" in style_token:
        return "bullet"
    if "number" in style_token:
        return "number"
    if "list" in style_token:
        return "list"
    return None


def _xml_int(xml_value, default: int | None = None) -> int | None:
    if xml_value is None:
        return default

    value = getattr(xml_value, "val", None)
    if value is None:
        return default

    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _extract_figures(
    paragraph: Paragraph, assets_dir: Path, figure_number: int
) -> tuple[list[dict], int]:
    figures: list[dict] = []

    for run_index, run in enumerate(paragraph.runs):
        blips = run._r.xpath(".//a:blip")
        for blip in blips:
            rel_id = blip.get(qn("r:embed")) or blip.get(qn("r:link"))
            if not rel_id:
                continue

            image_part = paragraph.part.related_parts.get(rel_id)
            if image_part is None:
                continue

            figure_number += 1
            image_path = _save_image_part(image_part, assets_dir, figure_number)
            figures.append(
                {
                    "figure_number": figure_number,
                    "image_path": str(image_path),
                    "content_type": image_part.content_type,
                    "filename": getattr(image_part, "filename", None),
                    "run_index": run_index,
                }
            )

    return figures, figure_number


def _save_image_part(image_part, assets_dir: Path, figure_number: int) -> Path:
    suffix = Path(getattr(image_part, "filename", "") or "").suffix
    if not suffix:
        suffix = mimetypes.guess_extension(getattr(image_part, "content_type", "")) or ".bin"

    image_path = assets_dir / f"docx_figure_{figure_number:04d}{suffix}"
    image_path.write_bytes(image_part.blob)
    return image_path


def _extract_table_rows(table: Table) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in table.rows:
        cells = [cell.text.strip() for cell in row.cells]
        rows.append(cells)
    return rows
