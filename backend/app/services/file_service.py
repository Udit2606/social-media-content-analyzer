"""Orchestrates one upload: validate, route to an extractor, package the result.

This is the only place that knows the *sequence* of operations. The route
handler stays thin and the extractors stay ignorant of HTTP, which keeps both
independently testable.

On temporary storage: there is none. PyMuPDF opens a PDF from a byte stream and
Pillow decodes an image from a BytesIO buffer, so nothing user-supplied is ever
written to disk. That removes an entire class of problem -- no cleanup to get
wrong, no leftover files if the process dies mid-request, no path traversal, and
nothing on disk that could be executed. Uploaded bytes are only ever parsed as
data, never run.
"""

import logging
import time
from typing import Tuple

from fastapi import UploadFile
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.schemas.analysis import (
    ExtractionResult,
    FileInfo,
    ProcessingInfo,
    UploadResponse,
)
from app.services import ocr_service, pdf_service
from app.utils import errors, file_validation

logger = logging.getLogger(__name__)


async def process_upload(upload: UploadFile) -> UploadResponse:
    """Validate and extract text from one uploaded file.

    Reading the request body is genuine async I/O and stays on the event loop.
    Everything after it -- PDF parsing, page rasterising, OCR -- is CPU-bound
    and is pushed onto a worker thread.

    That split matters more than it looks. FastAPI runs `async def` handlers
    directly on the event loop, so a synchronous call inside one stops the
    entire process: OCR on a multi-page scan takes seconds, during which no
    other request, not even /api/health, can be served. Offloading keeps the
    server responsive while a slow extraction runs.
    """
    started = time.perf_counter()

    filename = file_validation.sanitize_filename(upload.filename)
    content = await file_validation.read_upload_within_limit(upload, filename)

    return await run_in_threadpool(_extract_and_package, content, filename, started)


def _extract_and_package(
    content: bytes, filename: str, started: float
) -> UploadResponse:
    """The CPU-bound half. Runs in a worker thread, never on the event loop."""
    # The bytes decide what this is -- not the extension, not the header.
    kind, mime_type = file_validation.detect_file_kind(content, filename)

    if kind == "pdf":
        text, method, page_count, confidence, notes = _extract_from_pdf(content, filename)
    else:
        text, method, page_count, confidence, notes = _extract_from_image(content, filename)

    if not text.strip():
        raise errors.no_text_found(is_image=(kind == "image"))

    duration_ms = int((time.perf_counter() - started) * 1000)

    return UploadResponse(
        file=FileInfo(
            name=filename,
            kind=kind,
            size_bytes=len(content),
            mime_type=mime_type,
        ),
        extraction=ExtractionResult(
            method=method,
            text=text,
            page_count=page_count,
            word_count=len(text.split()),
            character_count=len(text),
            confidence=confidence,
        ),
        processing=ProcessingInfo(
            duration_ms=duration_ms,
            engine=_engine_for(method),
            notes=notes,
        ),
    )


# -- Extraction routing ----------------------------------------------------


def _extract_from_pdf(content: bytes, filename: str) -> Tuple:
    """Try native text first; fall back to OCR when the PDF is a scan.

    This fallback is the single most important behaviour in the service. A
    scanned PDF looks identical to a human and is completely empty to a parser,
    so without it a perfectly valid document would be reported as containing no
    text.
    """
    text, page_count = pdf_service.extract_text(content, filename)

    if page_count == 0:
        # Structurally valid but contains no pages at all. Routing this into
        # the OCR fallback would rasterise nothing and then report a
        # misleading "OCR unavailable" instead of the actual problem.
        raise errors.no_text_found(is_image=False)

    if not pdf_service.looks_scanned(text, page_count):
        return (
            text,
            "pdf_text",
            page_count,
            None,
            f"Extracted embedded text from {page_count} page(s).",
        )

    logger.info("PDF appears scanned; falling back to OCR: %s", filename)

    if not ocr_service.is_available():
        # Be explicit rather than silently returning the near-empty text.
        raise errors.ocr_unavailable()

    images = pdf_service.render_pages_to_images(content, filename)
    ocr_text, confidence = ocr_service.extract_text_from_images(images, filename)

    truncated = page_count > settings.max_ocr_pages
    note = (
        f"No embedded text found, so {len(images)} page(s) were rendered and "
        f"read with OCR."
    )
    if truncated:
        note += f" Only the first {settings.max_ocr_pages} pages were processed."

    return ocr_text, "ocr_pdf_fallback", page_count, confidence, note


def _extract_from_image(content: bytes, filename: str) -> Tuple:
    text, confidence = ocr_service.extract_text(content, filename)
    return (
        text,
        "ocr_image",
        None,
        confidence,
        "Image read with OCR.",
    )


def _engine_for(method: str) -> str:
    return "PyMuPDF" if method == "pdf_text" else "Tesseract OCR"
