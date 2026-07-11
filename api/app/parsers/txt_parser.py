from pathlib import Path


def parse_txt(file_path: Path, assets_dir: Path | None = None) -> dict:
    """Parse a plain-text file and return structured JSON."""
    content = file_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    return {
        "file_type": "txt",
        "content": content,
        "lines": lines,
        "metadata": {
            "total_lines": len(lines),
            "total_chars": len(content),
        },
    }
