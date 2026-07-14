from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str


class LLMClient:
    def __init__(self, provider: str | None = None, model: str | None = None) -> None:
        deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")
        detected_provider = provider or os.getenv("LLM_PROVIDER")
        if detected_provider is None and deepseek_api_key:
            detected_provider = "deepseek"
        self.provider = (detected_provider or "heuristic").lower()
        self.api_key = deepseek_api_key if self.provider == "deepseek" else None
        self.model = model or os.getenv("LLM_MODEL") or "deepseek-chat"
        self.base_url = os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com"

    def analyze(self, prompt: str, *, fallback: dict[str, Any]) -> dict[str, Any]:
        if self.provider == "heuristic":
            return fallback

        if self.provider == "deepseek":
            try:
                return self._analyze_deepseek(prompt, fallback=fallback)
            except Exception:
                return fallback

        return fallback

    def _analyze_deepseek(self, prompt: str, *, fallback: dict[str, Any]) -> dict[str, Any]:
        if not self.api_key:
            return fallback

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a precise educational content analyst. Return JSON only."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }

        request = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError:
            return fallback

        content = (
            raw.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        parsed = self._parse_json_content(content)
        if isinstance(parsed, dict):
            return self._normalize_result(parsed, fallback)
        return fallback

    def _parse_json_content(self, content: str) -> dict[str, Any] | None:
        content = content.strip()
        if not content:
            return None

        try:
            loaded = json.loads(content)
            return loaded if isinstance(loaded, dict) else None
        except json.JSONDecodeError:
            pass

        match = re.search(r"\{.*\}", content, flags=re.DOTALL)
        if not match:
            return None

        try:
            loaded = json.loads(match.group(0))
            return loaded if isinstance(loaded, dict) else None
        except json.JSONDecodeError:
            return None

    def _normalize_result(self, data: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
        result = dict(fallback)
        result["block_type"] = str(data.get("block_type") or result["block_type"])
        result["title"] = str(data.get("title") or result.get("title") or "")
        result["lead"] = str(data.get("lead") or result.get("lead") or "")
        result["summary"] = str(data.get("summary") or result["summary"])
        for key in ("paragraphs", "key_terms", "takeaways", "hints"):
            items = data.get(key)
            if isinstance(items, list):
                result[key] = [str(item) for item in items if str(item).strip()]
        questions = data.get("questions")
        if isinstance(questions, list):
            normalized_questions = self._normalize_questions(questions)
            if normalized_questions:
                result["questions"] = normalized_questions
        return result

    def _normalize_questions(self, questions: list[Any]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        option_ids = ["A", "B", "C", "D"]

        for item in questions:
            if not isinstance(item, dict):
                continue

            question = str(item.get("question") or "").strip()
            options = item.get("options")
            correct_option_id = str(item.get("correct_option_id") or "").strip().upper()
            explanation = str(item.get("explanation") or "").strip()
            if not question or not isinstance(options, list):
                continue

            normalized_options: list[dict[str, str]] = []
            for index, option in enumerate(options[:4]):
                if isinstance(option, dict):
                    option_text = str(option.get("text") or "").strip()
                    option_id = str(option.get("id") or option_ids[index]).strip().upper()
                else:
                    option_text = str(option).strip()
                    option_id = option_ids[index]

                if option_text:
                    normalized_options.append({"id": option_id, "text": option_text})

            if len(normalized_options) != 4:
                continue

            valid_ids = {option["id"] for option in normalized_options}
            if correct_option_id not in valid_ids:
                correct_option_id = normalized_options[0]["id"]

            normalized.append(
                {
                    "question": question,
                    "options": normalized_options,
                    "correct_option_id": correct_option_id,
                    "explanation": explanation,
                }
            )

        return normalized[:5]

    @staticmethod
    def dump_json(data: dict[str, Any]) -> str:
        return json.dumps(data, ensure_ascii=False)
