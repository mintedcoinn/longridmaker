from __future__ import annotations


def export_moodle(course: dict) -> dict:
    return {"format": "moodle", "course": course}

