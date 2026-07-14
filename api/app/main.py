import tempfile
import shutil
from urllib.parse import quote
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from .exporters import export_scorm
from .pipeline import Pipeline
from .pipeline.llm import LLMClient
from .parsers import (
    SUPPORTED_AUDIO_EXTENSIONS,
    AudioTranscriptionError,
    parse_audio,
    parse_docx,
    parse_pdf,
    parse_pptx,
    parse_txt,
)

app = FastAPI(title="File Parser API")
pipeline = Pipeline()
RUNTIME_ASSETS_ROOT = Path(__file__).resolve().parents[1] / "_runtime_assets"

PARSERS = {
    ".pdf": parse_pdf,
    ".pptx": parse_pptx,
    ".pptm": parse_pptx,
    ".docx": parse_docx,
    ".txt": parse_txt,
    **{extension: parse_audio for extension in SUPPORTED_AUDIO_EXTENSIONS},
}

SUPPORTED_EXTENSIONS = list(PARSERS.keys())


@app.get("/media")
async def media(path: str = Query(..., description="Path relative to the runtime assets directory")):
    """Serve extracted images from the project runtime directory."""
    relative_path = Path(path)
    if relative_path.is_absolute():
        raise HTTPException(status_code=403, detail="Access denied for this path")

    runtime_root = RUNTIME_ASSETS_ROOT.resolve()
    resolved = (runtime_root / relative_path).resolve(strict=True)
    if not resolved.is_relative_to(runtime_root):
        raise HTTPException(status_code=403, detail="Access denied for this path")

    return FileResponse(resolved)


@app.get("/formats")
async def formats():
    """Return the list of supported file extensions."""
    return {"supported_extensions": SUPPORTED_EXTENSIONS}


@app.get("/llm/status")
async def llm_status():
    """Show the currently detected LLM configuration."""
    client = LLMClient()
    return {
        "provider": client.provider,
        "model": client.model,
        "api_key_present": bool(client.api_key),
        "base_url": client.base_url,
    }


@app.post("/parse")
async def parse(file: UploadFile = File(...)):
    """Parse an uploaded file and return its content as JSON."""
    if file.filename is None:
        raise HTTPException(status_code=400, detail="No filename provided")

    suffix = Path(file.filename).suffix.lower()
    parser = PARSERS.get(suffix)

    if parser is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. "
            f"Supported: {', '.join(SUPPORTED_EXTENSIONS)}",
        )

    # Write uploaded bytes to a temp file so each parser can read lazily.
    content = await file.read()
    with tempfile.NamedTemporaryFile(
        suffix=suffix, delete=False
    ) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    assets_dir = _prepare_assets_dir()

    try:
        result = _run_parser(parser, tmp_path, assets_dir)
    finally:
        tmp_path.unlink(missing_ok=True)

    return _attach_media_urls({"filename": file.filename, **result})


@app.post("/pipeline")
async def run_pipeline(file: UploadFile = File(...)):
    """Parse an uploaded file and run it through the course pipeline."""
    if file.filename is None:
        raise HTTPException(status_code=400, detail="No filename provided")

    suffix = Path(file.filename).suffix.lower()
    parser = PARSERS.get(suffix)

    if parser is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. "
            f"Supported: {', '.join(SUPPORTED_EXTENSIONS)}",
        )

    content = await file.read()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    assets_dir = _prepare_assets_dir()

    try:
        parsed = _run_parser(parser, tmp_path, assets_dir)
        result = pipeline.run(parsed, source_file=file.filename)
    finally:
        tmp_path.unlink(missing_ok=True)

    return {"filename": file.filename, "pipeline": _attach_media_urls(result)}


@app.post("/export/scorm")
async def export_scorm_package(file: UploadFile = File(...)):
    """Parse an uploaded file, build a longread, and return a SCORM 1.2 package."""
    if file.filename is None:
        raise HTTPException(status_code=400, detail="No filename provided")

    suffix = Path(file.filename).suffix.lower()
    parser = PARSERS.get(suffix)

    if parser is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. "
            f"Supported: {', '.join(SUPPORTED_EXTENSIONS)}",
        )

    content = await file.read()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    assets_dir = _prepare_assets_dir()

    try:
        parsed = _run_parser(parser, tmp_path, assets_dir)
        course = pipeline.run(parsed, source_file=file.filename)
        package_path = export_scorm(course, output_dir=assets_dir)
    finally:
        tmp_path.unlink(missing_ok=True)

    return FileResponse(
        package_path,
        media_type="application/zip",
        filename=package_path.name,
    )


def _run_parser(parser, tmp_path: Path, assets_dir: Path) -> dict:
    try:
        return parser(tmp_path, assets_dir=assets_dir)
    except AudioTranscriptionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def _prepare_assets_dir() -> Path:
    """Create a clean runtime directory for extracted images."""
    if RUNTIME_ASSETS_ROOT.exists():
        for child in RUNTIME_ASSETS_ROOT.iterdir():
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)

    RUNTIME_ASSETS_ROOT.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="run-", dir=RUNTIME_ASSETS_ROOT))


def _attach_media_urls(value):
    if isinstance(value, list):
        return [_attach_media_urls(item) for item in value]

    if not isinstance(value, dict):
        return value

    normalized = {key: _attach_media_urls(item) for key, item in value.items()}
    image_path = normalized.get("image_path")
    if isinstance(image_path, str) and image_path.strip():
        relative_path = _to_runtime_relative_path(Path(image_path))
        if relative_path is not None:
            normalized["media_url"] = f"/api/media?path={quote(relative_path.as_posix(), safe='')}"
    return normalized


def _to_runtime_relative_path(image_path: Path) -> Path | None:
    runtime_root = RUNTIME_ASSETS_ROOT.resolve()
    try:
        resolved = image_path.resolve(strict=True)
    except FileNotFoundError:
        return None

    if not resolved.is_relative_to(runtime_root):
        return None

    return resolved.relative_to(runtime_root)
