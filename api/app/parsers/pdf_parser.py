from __future__ import annotations

import tempfile
from pathlib import Path

import pdfplumber


def parse_pdf(file_path: Path, assets_dir: Path | None = None) -> dict:
    """Parse a PDF file and return structured JSON with page-by-page text."""
    resolved_assets_dir = _resolve_assets_dir(assets_dir)
    pages = []
    image_number = 0

    with pdfplumber.open(file_path) as pdf:
        total_pages = len(pdf.pages)

        for page_index, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            page_images = []

            for page_image_index, image in enumerate(page.images, start=1):
                image_number += 1
                image_path = _save_pdf_image(
                    page=page,
                    image=image,
                    assets_dir=resolved_assets_dir,
                    page_number=page_index,
                    image_number=image_number,
                )

                page_images.append(
                    {
                        "image_number": image_number,
                        "page_image_number": page_image_index,
                        "image_path": str(image_path) if image_path else None,
                        "bbox": {
                            "x0": image.get("x0"),
                            "top": image.get("top"),
                            "x1": image.get("x1"),
                            "bottom": image.get("bottom"),
                            "width": image.get("width"),
                            "height": image.get("height"),
                        },
                        "name": image.get("name"),
                        "object_id": image.get("objid"),
                    }
                )

            pages.append(
                {
                    "page_number": page_index,
                    "text": text,
                    "images": page_images,
                }
            )

    return {
        "file_type": "pdf",
        "pages": pages,
        "metadata": {
            "total_pages": total_pages,
            "total_images": image_number,
            "assets_dir": str(resolved_assets_dir),
        },
    }


def _resolve_assets_dir(assets_dir: Path | None) -> Path:
    if assets_dir is not None:
        assets_dir.mkdir(parents=True, exist_ok=True)
        return assets_dir

    return Path(tempfile.mkdtemp(prefix="file-parser-pdf-assets-"))


def _save_pdf_image(
    page,
    image: dict,
    assets_dir: Path,
    page_number: int,
    image_number: int,
) -> Path | None:
    x0 = image.get("x0")
    top = image.get("top")
    x1 = image.get("x1")
    bottom = image.get("bottom")

    if None in (x0, top, x1, bottom):
        return None

    image_path = assets_dir / f"pdf_page_{page_number:04d}_image_{image_number:04d}.png"

    try:
        cropped_page = page.crop((x0, top, x1, bottom))
        rendered = cropped_page.to_image(resolution=150)
        if hasattr(rendered, "original"):
            rendered.original.save(image_path)
        else:
            rendered.save(str(image_path))
        return image_path
    except Exception:
        return None
