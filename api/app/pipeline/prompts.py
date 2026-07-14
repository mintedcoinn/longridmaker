from __future__ import annotations

SYSTEM_PROMPT = (
    "You transform lecture fragments into readable educational longread sections. "
    "Return concise, structured JSON only."
)

BLOCK_PROMPT = """Turn this lecture chunk into one readable longread section.

Classify it into one of:
- introduction
- theory
- examples
- conclusion

Return JSON with:
{{
  "block_type": "...",
  "title": "...",
  "lead": "...",
  "paragraphs": ["..."],
  "summary": "...",
  "key_terms": ["..."],
  "takeaways": ["..."],
  "hints": ["..."]
}}

Rules:
- Preserve the lecture's original meaning and important terminology.
- Rewrite oral or fragmented lecture text into clear article prose.
- Keep paragraphs short enough for web reading.
- Do not invent facts that are not supported by the chunk.
- Prefer the most pedagogically useful block type.
- Extract 3-7 important terms.
- Keep the summary short and concrete.
- Put comparison/classification content into concise prose; tables will be handled separately.

Chunk:
{chunk}
"""

QUIZ_PROMPT = """Create a short multiple-choice quiz for this educational longread.

Return JSON with:
{{
  "questions": [
    {{
      "question": "...",
      "options": [
        {{"id": "A", "text": "..."}},
        {{"id": "B", "text": "..."}},
        {{"id": "C", "text": "..."}},
        {{"id": "D", "text": "..."}}
      ],
      "correct_option_id": "A",
      "explanation": "..."
    }}
  ]
}}

Rules:
- Create 3-5 questions.
- Each question must have exactly 4 options.
- Only one option is correct.
- Check understanding of the longread's main ideas and terms, not tiny trivia.
- Do not invent facts that are not supported by the longread.
- Keep everything in the same language as the longread.

Longread:
{longread}
"""
