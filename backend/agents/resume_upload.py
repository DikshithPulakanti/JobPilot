"""Extract plain resume text from uploaded PDF or text files."""

from __future__ import annotations

import os
from io import BytesIO
from typing import Final

import fitz  # PyMuPDF — render pages for OCR
from PIL import Image
from pypdf import PdfReader
import pytesseract

MAX_RESUME_BYTES: Final[int] = 5 * 1024 * 1024  # 5 MiB

# Scanned PDFs: render up to this many pages (typical resume ≤ 5 pages).
_DEFAULT_OCR_MAX_PAGES = 20
# Balance quality vs CPU; 150–200 is usually enough for OCR.
_DEFAULT_OCR_DPI = 150


def extract_resume_text(filename: str, data: bytes) -> str:
    """
    Return UTF-8 text from a ``.pdf`` or plain-text file (``.txt``, ``.md``).

    Raises ``ValueError`` with a short message if the format is unsupported or text is empty.
    """
    if not data:
        raise ValueError("The uploaded file is empty.")

    if len(data) > MAX_RESUME_BYTES:
        raise ValueError(f"File is too large (max {MAX_RESUME_BYTES // (1024 * 1024)} MB).")

    name = (filename or "").lower().strip()

    if name.endswith(".pdf"):
        return _text_from_pdf(data)

    if name.endswith((".txt", ".text", ".md")):
        return data.decode("utf-8", errors="replace").strip()

    # No extension or unknown: try PDF magic, then UTF-8
    if data[:4] == b"%PDF":
        return _text_from_pdf(data)

    try:
        text = data.decode("utf-8", errors="strict").strip()
    except UnicodeDecodeError:
        raise ValueError(
            "Unsupported file type. Upload a PDF (.pdf) or plain text (.txt), "
            "or use POST /start with JSON field resume_text."
        ) from None

    if not text:
        raise ValueError(
            "Could not read text from this file. Try a PDF with selectable text or a .txt file."
        )
    return text


def _text_from_pdf(data: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(data))
    except Exception as exc:  # noqa: BLE001
        raise ValueError("Invalid or corrupted PDF.") from exc

    parts: list[str] = []
    for page in reader.pages:
        try:
            t = page.extract_text()
        except Exception:  # noqa: BLE001
            continue
        if t:
            parts.append(t)
    out = "\n".join(parts).strip()
    if out:
        return out

    # No embedded text — common for scanned / image-only PDFs; OCR each page.
    return _ocr_scanned_pdf(data)


def _ocr_scanned_pdf(data: bytes) -> str:
    """Render PDF pages to images and run Tesseract OCR."""
    max_pages = max(1, int(os.getenv("RESUME_OCR_MAX_PAGES", str(_DEFAULT_OCR_MAX_PAGES))))
    dpi = max(72, min(300, int(os.getenv("RESUME_OCR_DPI", str(_DEFAULT_OCR_DPI)))))
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)

    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:  # noqa: BLE001
        raise ValueError("Could not open this PDF for OCR (file may be corrupt).") from exc

    texts: list[str] = []
    try:
        n = min(doc.page_count, max_pages)
        if n < 1:
            raise ValueError("This PDF has no pages.")

        for i in range(n):
            page = doc.load_page(i)
            try:
                pix = page.get_pixmap(matrix=matrix, alpha=False)
            except Exception:  # noqa: BLE001
                continue
            try:
                img = Image.open(BytesIO(pix.tobytes("png")))
            except Exception:  # noqa: BLE001
                continue
            try:
                chunk = pytesseract.image_to_string(img, lang="eng")
            except pytesseract.TesseractNotFoundError as exc:
                raise ValueError(
                    "This PDF has no selectable text (likely a scan). Install the Tesseract OCR "
                    "engine on this machine: macOS `brew install tesseract`, Ubuntu/Debian "
                    "`apt install tesseract-ocr`, Windows: install from GitHub UB-Mannheim/tesseract "
                    "and ensure `tesseract` is on PATH. Alternatively paste resume text into "
                    "POST /start as resume_text."
                ) from exc
            if chunk and chunk.strip():
                texts.append(chunk.strip())
    finally:
        doc.close()

    out = "\n\n".join(texts).strip()
    if not out:
        raise ValueError(
            "OCR could not read text from this PDF. Try a higher-resolution scan, "
            "a PDF exported with a text layer, or paste plain text via POST /start."
        )
    return out
