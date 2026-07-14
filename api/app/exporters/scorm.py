from __future__ import annotations

import html
import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any


def export_scorm(course: dict, *, output_dir: Path | None = None) -> Path:
    """Create a SCORM 1.2 package for a generated longread."""
    package_dir = Path(tempfile.mkdtemp(prefix="longread-scorm-"))
    assets_dir = package_dir / "assets"
    images_dir = assets_dir / "images"
    assets_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)

    image_sources = _copy_images(course, images_dir)
    (package_dir / "index.html").write_text(
        _render_index_html(course, image_sources),
        encoding="utf-8",
    )
    (package_dir / "styles.css").write_text(_render_styles(), encoding="utf-8")
    (package_dir / "scorm.js").write_text(_render_scorm_runtime(), encoding="utf-8")
    (package_dir / "imsmanifest.xml").write_text(
        _render_manifest(course, package_dir),
        encoding="utf-8",
    )

    target_dir = output_dir or Path(tempfile.mkdtemp(prefix="longread-scorm-package-"))
    target_dir.mkdir(parents=True, exist_ok=True)
    zip_path = target_dir / f"{_slugify(str(course.get('title') or 'longread'))}-scorm.zip"

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in package_dir.rglob("*"):
            if file_path.is_file():
                archive.write(file_path, file_path.relative_to(package_dir).as_posix())

    shutil.rmtree(package_dir, ignore_errors=True)
    return zip_path


def _copy_images(course: dict, images_dir: Path) -> dict[str, str]:
    copied: dict[str, str] = {}

    for block in course.get("blocks", []):
        if not isinstance(block, dict):
            continue
        image_path = block.get("image_path") or block.get("metadata", {}).get("image_path")
        if not isinstance(image_path, str) or not image_path.strip():
            continue

        source = Path(image_path)
        try:
            resolved = source.resolve(strict=True)
        except FileNotFoundError:
            continue

        suffix = resolved.suffix or ".png"
        filename = f"image-{len(copied) + 1:03d}{suffix}"
        target = images_dir / filename
        shutil.copy2(resolved, target)
        copied[image_path] = f"assets/images/{filename}"

    return copied


def _render_index_html(course: dict, image_sources: dict[str, str]) -> str:
    title = _escape(str(course.get("title") or "Лонгрид"))
    blocks_html = "\n".join(_render_block(block, image_sources) for block in course.get("blocks", []))

    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <main class="longread">
    <header class="hero">
      <p class="eyebrow">Учебный лонгрид</p>
      <h1>{title}</h1>
      <p class="source">Источник: {_escape(str(course.get("source_file") or ""))}</p>
    </header>
    {blocks_html}
  </main>
  <script src="scorm.js"></script>
</body>
</html>
"""


def _render_block(block: Any, image_sources: dict[str, str]) -> str:
    if not isinstance(block, dict):
        return ""

    block_type = str(block.get("type") or "")
    if block_type == "quiz":
        return _render_quiz(block)
    if block_type == "table":
        return _render_table(block)
    if block_type == "image":
        return _render_image(block, image_sources)
    return _render_text_block(block)


def _render_text_block(block: dict) -> str:
    title = _escape(str(block.get("title") or "Раздел"))
    lead = str(block.get("lead") or "").strip()
    paragraphs = block.get("paragraphs")
    if not isinstance(paragraphs, list) or not paragraphs:
        paragraphs = [block.get("content") or block.get("summary") or ""]

    terms = block.get("key_terms")
    takeaways = block.get("takeaways")

    paragraphs_html = "\n".join(
        f"    <p>{_escape(str(paragraph))}</p>"
        for paragraph in paragraphs
        if str(paragraph).strip()
    )
    terms_html = _render_terms(terms)
    takeaways_html = _render_takeaways(takeaways)
    lead_html = f'    <p class="lead">{_escape(lead)}</p>' if lead else ""

    return f"""  <section class="section">
    <p class="block-type">{_escape(_block_label(str(block.get("type") or "")))}</p>
    <h2>{title}</h2>
{lead_html}
{paragraphs_html}
{terms_html}
{takeaways_html}
  </section>"""


def _render_table(block: dict) -> str:
    table = block.get("table") or block.get("metadata", {}).get("table") or {}
    headers = table.get("headers") if isinstance(table, dict) else []
    rows = table.get("rows") if isinstance(table, dict) else []
    headers = headers if isinstance(headers, list) else []
    rows = rows if isinstance(rows, list) else []

    header_html = "".join(f"<th>{_escape(str(header))}</th>" for header in headers)
    rows_html = "\n".join(
        "<tr>" + "".join(f"<td>{_escape(str(cell))}</td>" for cell in row) + "</tr>"
        for row in rows
        if isinstance(row, list)
    )

    return f"""  <section class="section">
    <p class="block-type">Таблица</p>
    <h2>{_escape(str(block.get("title") or "Таблица"))}</h2>
    <p class="muted">{_escape(str(block.get("summary") or ""))}</p>
    <div class="table-wrap">
      <table>
        <thead><tr>{header_html}</tr></thead>
        <tbody>
{rows_html}
        </tbody>
      </table>
    </div>
  </section>"""


def _render_image(block: dict, image_sources: dict[str, str]) -> str:
    image_path = block.get("image_path") or block.get("metadata", {}).get("image_path")
    src = image_sources.get(str(image_path), "")
    image_html = (
        f'    <img src="{_escape(src)}" alt="{_escape(str(block.get("summary") or block.get("title") or ""))}">'
        if src
        else '    <div class="image-placeholder">Изображение недоступно в пакете</div>'
    )

    return f"""  <section class="section">
    <p class="block-type">Иллюстрация</p>
    <h2>{_escape(str(block.get("title") or "Иллюстрация"))}</h2>
    <p class="muted">{_escape(str(block.get("summary") or ""))}</p>
{image_html}
  </section>"""


def _render_quiz(block: dict) -> str:
    quiz = block.get("quiz") or block.get("metadata", {}).get("quiz") or {}
    questions = quiz.get("questions") if isinstance(quiz, dict) else []
    if not isinstance(questions, list):
        questions = []

    questions_html = []
    for question_index, question in enumerate(questions):
        if not isinstance(question, dict):
            continue
        options = question.get("options") if isinstance(question.get("options"), list) else []
        options_html = "\n".join(
            _render_quiz_option(question_index, option)
            for option in options
            if isinstance(option, dict)
        )
        correct_id = _escape(str(question.get("correct_option_id") or ""))
        explanation = _escape(str(question.get("explanation") or ""))
        questions_html.append(
            f"""      <fieldset class="quiz-question" data-correct="{correct_id}" data-explanation="{explanation}">
        <legend>{question_index + 1}. {_escape(str(question.get("question") or ""))}</legend>
{options_html}
        <p class="quiz-feedback" aria-live="polite"></p>
      </fieldset>"""
        )

    quiz_payload = _escape(json.dumps(questions, ensure_ascii=False))
    return f"""  <section class="section quiz" id="quiz" data-quiz="{quiz_payload}">
    <p class="block-type">Мини-квиз</p>
    <h2>{_escape(str(block.get("title") or "Мини-квиз"))}</h2>
    <p class="lead">{_escape(str(block.get("lead") or block.get("summary") or ""))}</p>
    <form id="quiz-form">
{chr(10).join(questions_html)}
    </form>
    <div class="quiz-result" id="quiz-result">Ответь на вопросы, чтобы Moodle получил балл.</div>
  </section>"""


def _render_quiz_option(question_index: int, option: dict) -> str:
    option_id = _escape(str(option.get("id") or ""))
    option_text = _escape(str(option.get("text") or ""))
    input_id = f"q{question_index}-{option_id}"
    return f"""        <label class="quiz-option" for="{input_id}">
          <input id="{input_id}" type="radio" name="q{question_index}" value="{option_id}">
          <span>{option_id}. {option_text}</span>
        </label>"""


def _render_terms(terms: Any) -> str:
    if not isinstance(terms, list) or not terms:
        return ""
    chips = "".join(f'<span class="chip">{_escape(str(term))}</span>' for term in terms)
    return f'    <div class="chips">{chips}</div>'


def _render_takeaways(takeaways: Any) -> str:
    if not isinstance(takeaways, list) or not takeaways:
        return ""
    items = "".join(f"<li>{_escape(str(item))}</li>" for item in takeaways)
    return f"""    <aside class="takeaways">
      <strong>Главное</strong>
      <ul>{items}</ul>
    </aside>"""


def _render_styles() -> str:
    return """
:root {
  color: #17202a;
  background: #f4f6f8;
  font-family: Inter, Arial, sans-serif;
}
* { box-sizing: border-box; }
body { margin: 0; }
.longread {
  width: min(960px, calc(100% - 32px));
  margin: 0 auto;
  padding: 32px 0 56px;
}
.hero, .section {
  margin-bottom: 18px;
  padding: 28px;
  border: 1px solid #dbe1e8;
  border-radius: 8px;
  background: #fff;
}
.eyebrow, .block-type {
  margin: 0 0 8px;
  color: #315f72;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: .08em;
  text-transform: uppercase;
}
h1, h2 { margin: 0 0 12px; line-height: 1.15; }
h1 { font-size: clamp(32px, 6vw, 56px); }
h2 { font-size: clamp(24px, 4vw, 34px); }
p { line-height: 1.72; }
.lead { color: #415165; font-size: 18px; }
.muted, .source { color: #607080; }
.chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 18px; }
.chip {
  padding: 5px 10px;
  border: 1px solid #b9c5cf;
  border-radius: 999px;
  font-size: 13px;
}
.takeaways {
  margin-top: 18px;
  padding: 14px 16px;
  border-left: 4px solid #4f7c8a;
  border-radius: 6px;
  background: #f3f7f8;
}
.takeaways ul { margin: 8px 0 0; padding-left: 20px; }
.table-wrap { overflow-x: auto; border: 1px solid #dbe1e8; border-radius: 8px; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 10px 12px; border-bottom: 1px solid #e4e9ee; text-align: left; vertical-align: top; }
th { background: #eef4f5; }
img { width: 100%; max-height: 560px; object-fit: contain; border: 1px solid #dbe1e8; border-radius: 8px; }
.image-placeholder {
  min-height: 220px;
  display: grid;
  place-items: center;
  border: 1px dashed #a8b4c0;
  border-radius: 8px;
  color: #596879;
  background: #f4f6f8;
}
.quiz-question {
  margin: 16px 0;
  padding: 16px;
  border: 1px solid #dbe1e8;
  border-radius: 8px;
}
.quiz-question legend { font-weight: 700; }
.quiz-option {
  display: flex;
  gap: 8px;
  margin: 8px 0;
  padding: 9px 10px;
  border: 1px solid #dbe1e8;
  border-radius: 6px;
  cursor: pointer;
}
.quiz-option.is-correct { border-color: #6aa278; background: #edf7ef; }
.quiz-option.is-wrong { border-color: #c57a74; background: #fff1f0; }
.quiz-feedback, .quiz-result {
  margin-top: 12px;
  padding: 12px 14px;
  border-radius: 6px;
  background: #eef4f5;
}
"""


def _render_scorm_runtime() -> str:
    return r"""
(function () {
  var api = null;
  var initialized = false;
  var quizCompleted = false;
  var startTime = new Date();

  function findApi(win) {
    var attempts = 0;
    while (win && attempts < 500) {
      if (win.API) return win.API;
      if (win.parent === win) break;
      attempts += 1;
      win = win.parent;
    }
    if (window.opener && window.opener.API) return window.opener.API;
    return null;
  }

  function initialize() {
    api = findApi(window);
    if (!api) return;
    var result = api.LMSInitialize("");
    initialized = result === true || result === "true";
    if (initialized) {
      setValue("cmi.core.lesson_status", "incomplete");
      commit();
    }
  }

  function setValue(key, value) {
    if (!initialized || !api) return;
    api.LMSSetValue(key, String(value));
  }

  function commit() {
    if (!initialized || !api) return;
    api.LMSCommit("");
  }

  function finish() {
    if (!initialized || !api) return;
    setValue("cmi.core.session_time", formatSessionTime(new Date() - startTime));
    commit();
    if (typeof api.LMSFinish === "function") {
      api.LMSFinish("");
    }
    initialized = false;
  }

  function formatSessionTime(milliseconds) {
    var totalSeconds = Math.max(0, Math.floor(milliseconds / 1000));
    var hours = Math.floor(totalSeconds / 3600);
    var minutes = Math.floor((totalSeconds % 3600) / 60);
    var seconds = totalSeconds % 60;
    return pad(hours, 2) + ":" + pad(minutes, 2) + ":" + pad(seconds, 2);
  }

  function pad(value, length) {
    var text = String(value);
    while (text.length < length) text = "0" + text;
    return text;
  }

  function setupQuiz() {
    var quiz = document.querySelector(".quiz");
    if (!quiz) return;

    quiz.addEventListener("change", function () {
      gradeQuiz(quiz);
    });
  }

  function gradeQuiz(quiz) {
    var questions = Array.prototype.slice.call(quiz.querySelectorAll(".quiz-question"));
    if (!questions.length) return;

    var answered = 0;
    var correct = 0;

    questions.forEach(function (question) {
      var selected = question.querySelector("input[type=radio]:checked");
      var correctId = question.getAttribute("data-correct");
      var explanation = question.getAttribute("data-explanation") || "";
      var feedback = question.querySelector(".quiz-feedback");

      Array.prototype.forEach.call(question.querySelectorAll(".quiz-option"), function (label) {
        label.classList.remove("is-correct", "is-wrong");
        var input = label.querySelector("input");
        if (!input || !selected) return;
        if (input.value === correctId) label.classList.add("is-correct");
        if (input.checked && input.value !== correctId) label.classList.add("is-wrong");
      });

      if (!selected) {
        if (feedback) feedback.textContent = "";
        return;
      }

      answered += 1;
      if (selected.value === correctId) {
        correct += 1;
        if (feedback) feedback.textContent = "Верно. " + explanation;
      } else if (feedback) {
        feedback.textContent = "Нужно повторить. " + explanation;
      }
    });

    var score = Math.round((correct / questions.length) * 100);
    var result = document.getElementById("quiz-result");
    if (result) {
      result.textContent = "Результат: " + correct + " из " + questions.length + " (" + score + "%).";
    }

    setValue("cmi.core.score.raw", score);
    if (answered === questions.length) {
      quizCompleted = true;
      setValue("cmi.core.lesson_status", score >= 70 ? "passed" : "failed");
    } else {
      setValue("cmi.core.lesson_status", "incomplete");
    }
    setValue("cmi.core.session_time", formatSessionTime(new Date() - startTime));
    commit();
  }

  window.addEventListener("load", function () {
    initialize();
    setupQuiz();
  });

  window.addEventListener("beforeunload", function () {
    if (!quizCompleted) {
      setValue("cmi.core.lesson_status", "incomplete");
    }
    finish();
  });
})();
"""


def _render_manifest(course: dict, package_dir: Path) -> str:
    title = _escape_xml(str(course.get("title") or "Лонгрид"))
    identifier = _slugify(str(course.get("title") or "longread"))
    files = []
    for file_path in sorted(package_dir.rglob("*")):
        if file_path.is_file() and file_path.name != "imsmanifest.xml":
            href = _escape_xml(file_path.relative_to(package_dir).as_posix())
            files.append(f'      <file href="{href}"/>')
    files_xml = "\n".join(files)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<manifest identifier="{identifier}" version="1.0"
  xmlns="http://www.imsproject.org/xsd/imscp_rootv1p1p2"
  xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_rootv1p2"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://www.imsproject.org/xsd/imscp_rootv1p1p2 imscp_rootv1p1p2.xsd
                      http://www.adlnet.org/xsd/adlcp_rootv1p2 adlcp_rootv1p2.xsd">
  <metadata>
    <schema>ADL SCORM</schema>
    <schemaversion>1.2</schemaversion>
  </metadata>
  <organizations default="org-1">
    <organization identifier="org-1">
      <title>{title}</title>
      <item identifier="item-1" identifierref="resource-1">
        <title>{title}</title>
      </item>
    </organization>
  </organizations>
  <resources>
    <resource identifier="resource-1" type="webcontent" adlcp:scormtype="sco" href="index.html">
{files_xml}
    </resource>
  </resources>
</manifest>
"""


def _block_label(block_type: str) -> str:
    return {
        "introduction": "Введение",
        "theory": "Теория",
        "examples": "Пример",
        "conclusion": "Вывод",
    }.get(block_type, "Раздел")


def _escape(value: str) -> str:
    return html.escape(value, quote=True)


def _escape_xml(value: str) -> str:
    return html.escape(value, quote=True)


def _slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9а-яё]+", "-", value, flags=re.IGNORECASE)
    value = value.strip("-")
    return value or "longread"
