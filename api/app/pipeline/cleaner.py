from __future__ import annotations

import re

_PLACEHOLDER_RE = re.compile(
    r"\b(?:"
    r"Title|Subtitle|Picture|Content Placeholder|Text Placeholder|"
    r"ContentPlaceholder|TextBox|Text Box|Object|Table|Chart|Diagram"
    r")\s+\d+\b",
    flags=re.IGNORECASE,
)


class TextCleaner:
    def clean(self, text: str) -> str:
        text = text.replace("\u00a0", " ")
        text = self._remove_layout_placeholders(text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _remove_layout_placeholders(self, text: str) -> str:
        cleaned_lines: list[str] = []
        for line in text.splitlines():
            cleaned = _PLACEHOLDER_RE.sub("", line)
            cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).strip()
            if cleaned:
                cleaned_lines.append(cleaned)
        return "\n".join(cleaned_lines)
