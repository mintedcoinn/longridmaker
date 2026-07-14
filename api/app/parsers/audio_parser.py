from __future__ import annotations

import os
from pathlib import Path
from typing import Any


SUPPORTED_AUDIO_EXTENSIONS = [".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm"]
DEFAULT_TRANSCRIPTION_MODEL = "whisper-1"
DEFAULT_MAX_AUDIO_BYTES = 25 * 1024 * 1024


class AudioTranscriptionError(RuntimeError):
    """Raised when an audio file cannot be transcribed."""


def parse_audio(file_path: Path, assets_dir: Path | None = None) -> dict:
    """Transcribe an audio lecture with OpenAI Whisper and return parser-style JSON."""
    suffix = file_path.suffix.lower()
    if suffix not in SUPPORTED_AUDIO_EXTENSIONS:
        raise AudioTranscriptionError(f"Unsupported audio type '{suffix}'")

    max_bytes = _env_int("OPENAI_TRANSCRIPTION_MAX_BYTES", DEFAULT_MAX_AUDIO_BYTES)
    file_size = file_path.stat().st_size
    if file_size > max_bytes:
        limit_mb = max_bytes / (1024 * 1024)
        raise AudioTranscriptionError(
            f"Audio file is too large for transcription. Limit: {limit_mb:.0f} MB."
        )

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise AudioTranscriptionError("OPENAI_API_KEY is required for audio transcription.")

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise AudioTranscriptionError(
            "The 'openai' package is required. Install backend requirements first."
        ) from exc

    model = os.getenv("OPENAI_WHISPER_MODEL") or DEFAULT_TRANSCRIPTION_MODEL
    language = _optional_env("OPENAI_TRANSCRIPTION_LANGUAGE")
    prompt = _optional_env("OPENAI_TRANSCRIPTION_PROMPT")

    request_args: dict[str, Any] = {
        "model": model,
        "response_format": "verbose_json",
    }
    if language:
        request_args["language"] = language
    if prompt:
        request_args["prompt"] = prompt

    client = OpenAI(api_key=api_key)
    try:
        with file_path.open("rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                file=audio_file,
                **request_args,
            )
    except Exception as exc:
        raise AudioTranscriptionError(f"OpenAI transcription failed: {exc}") from exc

    data = _to_plain_dict(transcription)
    content = str(data.get("text") or "").strip()
    if not content:
        raise AudioTranscriptionError("OpenAI returned an empty transcription.")

    segments = _normalize_segments(data.get("segments"))

    return {
        "file_type": "audio",
        "content": content,
        "segments": segments,
        "metadata": {
            "audio_extension": suffix,
            "model": model,
            "language": data.get("language") or language,
            "duration": data.get("duration"),
            "total_chars": len(content),
            "segment_count": len(segments),
            "file_size_bytes": file_size,
        },
    }


def _optional_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if not value:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _to_plain_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        return dumped if isinstance(dumped, dict) else {}
    text = getattr(value, "text", None)
    return {"text": text} if text is not None else {}


def _normalize_segments(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []

    normalized: list[dict[str, Any]] = []
    for item in value:
        segment = _to_plain_dict(item)
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        normalized.append(
            {
                "id": segment.get("id"),
                "start": segment.get("start"),
                "end": segment.get("end"),
                "text": text,
            }
        )
    return normalized
