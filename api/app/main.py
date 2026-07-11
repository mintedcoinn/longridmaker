import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile

from .parsers import parse_docx, parse_pdf, parse_pptx, parse_txt

app = FastAPI(title="File Parser API")

PARSERS = {
    ".pdf": parse_pdf,
    ".pptx": parse_pptx,
    ".pptm": parse_pptx,
    ".docx": parse_docx,
    ".txt": parse_txt,
}

SUPPORTED_EXTENSIONS = list(PARSERS.keys())


@app.get("/formats")
async def formats():
    """Return the list of supported file extensions."""
    return {"supported_extensions": SUPPORTED_EXTENSIONS}


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

    assets_dir = Path(tempfile.mkdtemp(prefix="file-parser-assets-"))

    try:
        result = parser(tmp_path, assets_dir=assets_dir)
    finally:
        tmp_path.unlink(missing_ok=True)

    return {"filename": file.filename, **result}
