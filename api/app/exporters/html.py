from __future__ import annotations


def export_html(course: dict) -> str:
    parts = ["<html><body>"]
    parts.append(f"<h1>{course.get('title', 'Course')}</h1>")
    for block in course.get("blocks", []):
        parts.append(f"<section><h2>{block.get('title', '')}</h2><p>{block.get('summary', '')}</p></section>")
    parts.append("</body></html>")
    return "\n".join(parts)

