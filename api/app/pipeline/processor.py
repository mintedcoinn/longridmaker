from __future__ import annotations

import re
import unicodedata

from .llm import LLMClient
from .prompts import BLOCK_PROMPT, QUIZ_PROMPT

_STOPWORDS = {
    "это",
    "как",
    "для",
    "или",
    "что",
    "при",
    "его",
    "она",
    "они",
    "оно",
    "уже",
    "если",
    "также",
    "когда",
    "можно",
    "нужно",
    "данных",
    "данные",
    "который",
    "которая",
    "которые",
    "the",
    "and",
    "with",
    "from",
    "that",
    "this",
}


class ChunkProcessor:
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm = llm_client or LLMClient()

    def process(self, chunk_text: str) -> dict:
        fallback = self._heuristic_analysis(chunk_text)
        prompt = BLOCK_PROMPT.format(chunk=chunk_text)
        return self.llm.analyze(prompt, fallback=fallback)

    def build_quiz(self, sections: list[dict], *, max_questions: int = 5) -> dict:
        fallback = {"questions": self._heuristic_quiz(sections, max_questions=max_questions)}
        longread = self._quiz_context(sections)
        if not longread:
            return fallback

        prompt = QUIZ_PROMPT.format(longread=longread)
        return self.llm.analyze(prompt, fallback=fallback)

    def _heuristic_analysis(self, text: str) -> dict:
        lowered = self._normalize_text(text)
        keywords = self._extract_terms(text)
        block_type = self._detect_block_type(lowered)
        paragraphs = self._build_paragraphs(text)
        return {
            "block_type": block_type,
            "title": self._build_title(text, block_type),
            "lead": self._build_lead(paragraphs, keywords),
            "paragraphs": paragraphs,
            "summary": self._build_summary(paragraphs),
            "key_terms": keywords[:7],
            "takeaways": self._build_takeaways(paragraphs, keywords),
            "hints": self._build_hints(block_type, keywords),
        }

    def _detect_block_type(self, text: str) -> str:
        if any(token in text for token in ["введение", "introduction", "цель", "задачи"]):
            return "introduction"
        if any(token in text for token in ["пример", "example", "case", "например", "рассмотрим"]):
            return "examples"
        if any(token in text for token in ["вывод", "заключение", "summary", "итог"]):
            return "conclusion"
        return "theory"

    def _extract_terms(self, text: str) -> list[str]:
        words = re.findall(r"[A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9_-]{3,}", text)
        seen: list[str] = []
        for word in words:
            normalized = word.strip(".,:;!?()[]{}").lower()
            if normalized in _STOPWORDS:
                continue
            if normalized not in seen:
                seen.append(normalized)
        return seen[:10]

    def _build_hints(self, block_type: str, terms: list[str]) -> list[str]:
        if block_type == "introduction":
            return ["Сфокусируйся на цели темы и вопросах, на которые дальше отвечает материал."]
        if block_type == "examples":
            return ["Свяжи пример с правилом, термином или алгоритмом, который он поясняет."]
        if block_type == "conclusion":
            return ["Сверь выводы с основными терминами из предыдущих разделов."]
        if terms:
            return [f"Обрати внимание на термины: {', '.join(terms[:3])}."]
        return ["Выдели ключевую идею раздела и сформулируй ее одним предложением."]

    def _normalize_text(self, text: str) -> str:
        return unicodedata.normalize("NFKC", text).lower()

    def _build_title(self, text: str, block_type: str) -> str:
        lines = [line.strip(" #\t") for line in text.splitlines() if line.strip()]
        for line in lines:
            if 8 <= len(line) <= 90 and not line.endswith((".", "!", "?")):
                return line

        first_sentence = self._first_sentence(text)
        if first_sentence:
            return self._shorten(first_sentence, 72)

        defaults = {
            "introduction": "Введение в тему",
            "theory": "Ключевая идея",
            "examples": "Пример из лекции",
            "conclusion": "Выводы",
        }
        return defaults.get(block_type, "Раздел лонгрида")

    def _build_lead(self, paragraphs: list[str], terms: list[str]) -> str:
        if paragraphs:
            return self._shorten(paragraphs[0], 220)
        if terms:
            return f"Раздел раскрывает понятия: {', '.join(terms[:3])}."
        return "Раздел продолжает основную мысль лекции."

    def _build_paragraphs(self, text: str) -> list[str]:
        normalized = re.sub(r"\r\n?", "\n", text)
        raw_parts = [part.strip() for part in re.split(r"\n{2,}", normalized) if part.strip()]
        if len(raw_parts) <= 1:
            raw_parts = self._split_into_sentences(normalized)

        paragraphs: list[str] = []
        current: list[str] = []
        current_len = 0

        for part in raw_parts:
            cleaned = self._clean_paragraph(part)
            if not cleaned:
                continue

            if current and current_len + len(cleaned) > 520:
                paragraphs.append(" ".join(current))
                current = []
                current_len = 0

            current.append(cleaned)
            current_len += len(cleaned) + 1

        if current:
            paragraphs.append(" ".join(current))

        return paragraphs[:8] or [self._clean_paragraph(text)]

    def _build_summary(self, paragraphs: list[str]) -> str:
        if not paragraphs:
            return ""
        return self._shorten(paragraphs[0], 280)

    def _build_takeaways(self, paragraphs: list[str], terms: list[str]) -> list[str]:
        takeaways: list[str] = []
        for paragraph in paragraphs[:3]:
            sentence = self._first_sentence(paragraph)
            if sentence:
                takeaways.append(self._shorten(sentence, 160))

        if terms:
            takeaways.append(f"Ключевые термины: {', '.join(terms[:4])}.")

        deduplicated: list[str] = []
        for item in takeaways:
            if item not in deduplicated:
                deduplicated.append(item)
        return deduplicated[:4]

    def _clean_paragraph(self, text: str) -> str:
        text = re.sub(r"\s+", " ", text).strip()
        text = re.sub(r"^[\-•\d.)\s]+", "", text).strip()
        return text

    def _split_into_sentences(self, text: str) -> list[str]:
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            return []
        sentences = re.split(r"(?<=[.!?])\s+", text)
        parts: list[str] = []
        current: list[str] = []
        current_len = 0
        for sentence in sentences:
            if current and current_len + len(sentence) > 420:
                parts.append(" ".join(current))
                current = []
                current_len = 0
            current.append(sentence)
            current_len += len(sentence) + 1
        if current:
            parts.append(" ".join(current))
        return parts

    def _first_sentence(self, text: str) -> str:
        parts = self._split_into_sentences(text)
        return parts[0] if parts else ""

    def _shorten(self, text: str, max_len: int) -> str:
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) <= max_len:
            return text
        shortened = text[: max_len - 1].rsplit(" ", 1)[0].strip()
        return f"{shortened}."

    def _heuristic_quiz(self, sections: list[dict], *, max_questions: int) -> list[dict]:
        candidates = [section for section in sections if section.get("type") not in {"image", "table", "quiz"}]
        questions: list[dict] = []

        for section in candidates:
            if len(questions) >= max_questions:
                break

            terms = self._list_from(section.get("key_terms"))
            takeaways = self._list_from(section.get("takeaways"))
            title = str(section.get("title") or "").strip()
            summary = str(section.get("summary") or section.get("lead") or "").strip()

            if terms:
                term = terms[0]
                question = f"Какой термин является ключевым для раздела «{title}»?"
                correct = term
                distractors = self._distractors(term, sections, terms)
                questions.append(
                    self._quiz_question(
                        question=question,
                        correct=correct,
                        distractors=distractors,
                        explanation=f"В разделе «{title}» этот термин выделен среди ключевых понятий.",
                    )
                )

            if len(questions) >= max_questions:
                break

            if summary:
                question = f"Какая идея лучше всего передает смысл раздела «{title}»?"
                correct = self._shorten(summary, 130)
                distractors = self._summary_distractors(section, sections)
                questions.append(
                    self._quiz_question(
                        question=question,
                        correct=correct,
                        distractors=distractors,
                        explanation=f"Эта формулировка соответствует краткому содержанию раздела «{title}».",
                    )
                )

            if len(questions) >= max_questions:
                break

            if takeaways:
                question = f"Что важно запомнить из раздела «{title}»?"
                correct = self._shorten(takeaways[0], 130)
                distractors = self._summary_distractors(section, sections)
                questions.append(
                    self._quiz_question(
                        question=question,
                        correct=correct,
                        distractors=distractors,
                        explanation="Правильный вариант повторяет главный вывод раздела.",
                    )
                )

            if len(questions) >= 3:
                break

        if len(questions) < 3:
            extra_terms: list[str] = []
            for section in candidates:
                for term in self._list_from(section.get("key_terms")):
                    if term not in extra_terms:
                        extra_terms.append(term)

            for term in extra_terms[1:]:
                if len(questions) >= min(max_questions, 3):
                    break
                questions.append(
                    self._quiz_question(
                        question=f"Какое понятие связано с основной темой лонгрида?",
                        correct=term,
                        distractors=self._distractors(term, sections, extra_terms),
                        explanation="Этот термин встречается среди ключевых понятий материала.",
                    )
                )

        if not questions and candidates:
            section = candidates[0]
            questions.append(
                self._quiz_question(
                    question="Что проверяет этот лонгрид?",
                    correct=self._shorten(str(section.get("summary") or section.get("title") or "Основную мысль лекции"), 130),
                    distractors=[
                        "Только порядок страниц исходного файла",
                        "Только оформление презентации",
                        "Только количество изображений",
                    ],
                    explanation="Квиз строится по содержанию лонгрида, а не по техническим деталям файла.",
                )
            )

        return questions[:max_questions]

    def _quiz_context(self, sections: list[dict]) -> str:
        parts: list[str] = []
        for section in sections:
            if section.get("type") in {"image", "quiz"}:
                continue
            title = str(section.get("title") or "").strip()
            summary = str(section.get("summary") or "").strip()
            terms = ", ".join(self._list_from(section.get("key_terms"))[:5])
            takeaways = " ".join(self._list_from(section.get("takeaways"))[:3])
            text = "\n".join(part for part in [title, summary, terms, takeaways] if part)
            if text:
                parts.append(text)
        return "\n\n".join(parts[:12])

    def _quiz_question(
        self,
        *,
        question: str,
        correct: str,
        distractors: list[str],
        explanation: str,
    ) -> dict:
        options_text = [correct]
        for distractor in distractors:
            cleaned = str(distractor).strip()
            if cleaned and cleaned not in options_text:
                options_text.append(cleaned)
            if len(options_text) == 4:
                break

        fallback_options = [
            "Второстепенная деталь оформления",
            "Фрагмент без связи с темой",
            "Техническое свойство файла",
        ]
        for fallback in fallback_options:
            if len(options_text) == 4:
                break
            if fallback not in options_text:
                options_text.append(fallback)

        correct_index = self._stable_correct_index(question)
        options_text[0], options_text[correct_index] = options_text[correct_index], options_text[0]
        option_ids = ["A", "B", "C", "D"]
        return {
            "question": question,
            "options": [
                {"id": option_id, "text": text}
                for option_id, text in zip(option_ids, options_text, strict=True)
            ],
            "correct_option_id": option_ids[correct_index],
            "explanation": explanation,
        }

    def _distractors(self, correct: str, sections: list[dict], local_terms: list[str]) -> list[str]:
        values: list[str] = []
        for term in local_terms[1:]:
            if term != correct:
                values.append(term)
        for section in sections:
            for term in self._list_from(section.get("key_terms")):
                if term != correct and term not in values:
                    values.append(term)
        values.extend(["иллюстрация", "оглавление", "формат файла"])
        return values

    def _summary_distractors(self, current: dict, sections: list[dict]) -> list[str]:
        values: list[str] = []
        for section in sections:
            if section is current:
                continue
            summary = str(section.get("summary") or section.get("title") or "").strip()
            if summary:
                values.append(self._shorten(summary, 130))
        values.extend(
            [
                "Материал посвящен только технической загрузке файла.",
                "Главная задача раздела - перечислить все изображения без объяснений.",
                "Раздел не связан с общей мыслью лекции.",
            ]
        )
        return values

    def _stable_correct_index(self, value: str) -> int:
        return sum(ord(char) for char in value) % 4

    def _list_from(self, value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]
