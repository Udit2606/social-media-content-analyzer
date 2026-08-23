"""PDF text extraction with PyMuPDF.

A PDF is not a document in the way a .txt file is. It is a set of drawing
instructions: "place these glyphs at these coordinates in this font". There is
no stored notion of a paragraph, or reliably even of a word. Extraction means
reconstructing human reading order from positioned glyphs.

PyMuPDF's "blocks" mode does the hard part -- it groups glyphs into positioned
text blocks. This module then orders those blocks top-to-bottom, left-to-right
and joins them with blank lines, which is what preserves paragraph structure.
That structure matters downstream: line breaks are part of what makes a social
post readable, so throwing them away would discard real signal.

Everything happens in memory. The uploaded bytes are never written to disk and
are never executed.
"""

import logging
import re
from typing import List, Tuple

import fitz  # PyMuPDF

from app.config import settings
from app.utils import errors

logger = logging.getLogger(__name__)

# Index positions in PyMuPDF's block tuples: (x0, y0, x1, y1, text, block_no, block_type)
_Y0, _X0, _TEXT, _BLOCK_TYPE = 1, 0, 4, 6
_TEXT_BLOCK = 0


def extract_text(content: bytes, filename: str) -> Tuple[str, int]:
    """Extract text from a PDF held in memory.

    Returns (text, page_count). The text may be empty -- that is a valid result
    meaning "this is a scanned PDF", and the caller decides whether to fall
    back to OCR.

    Raises AppError for encrypted or unreadable files.
    """
    document = _open_document(content, filename)

    try:
        page_count = document.page_count
        pages: List[str] = []

        for page in document:
            pages.append(_extract_page(page))

        # Pages are joined with a blank line: enough to keep them visually
        # separate without inventing a separator the user never wrote.
        text = "\n\n".join(part for part in pages if part.strip())
        return _normalise(text), page_count
    finally:
        document.close()


def render_pages_to_images(content: bytes, filename: str, dpi: int = 200) -> List[bytes]:
    """Rasterise each page to PNG bytes, for the scanned-PDF OCR fallback.

    Capped at settings.max_ocr_pages: rendering and OCR-ing an arbitrary number
    of pages is the easiest way to pin this server's CPU, so a hostile
    5,000-page upload is truncated rather than obeyed.
    """
    document = _open_document(content, filename)

    try:
        images: List[bytes] = []
        limit = min(document.page_count, settings.max_ocr_pages)

        for index in range(limit):
            page = document.load_page(index)
            # A zoom matrix upscales the render. OCR accuracy depends heavily
            # on input resolution; 200 DPI is the usual sweet spot between
            # accuracy and processing time.
            zoom = dpi / 72
            pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            images.append(pixmap.tobytes("png"))

        return images
    finally:
        document.close()


def looks_scanned(text: str, page_count: int) -> bool:
    """Decide whether a PDF is a scan wearing a PDF extension.

    A digital PDF exports real text objects. A scanned one contains a single
    image per page and yields an empty string, which would otherwise be
    reported as a successful extraction of nothing.
    """
    if page_count <= 0:
        return True
    return len(text.strip()) < settings.scanned_pdf_char_threshold * page_count


# -- Internals -------------------------------------------------------------


def _open_document(content: bytes, filename: str) -> "fitz.Document":
    """Open from a byte stream. Never touches the filesystem."""
    try:
        document = fitz.open(stream=content, filetype="pdf")
    except Exception:
        # Log the real reason for debugging; tell the user something useful.
        logger.warning("Failed to open PDF", exc_info=True)
        raise errors.corrupted_file(filename)

    if document.needs_pass:
        document.close()
        raise errors.password_protected(filename)

    return document


def _extract_page(page: "fitz.Page") -> str:
    """Rebuild one page's reading order from positioned text blocks."""
    blocks = page.get_text("blocks")

    # Keep text blocks only; type 1 blocks are images.
    text_blocks = [b for b in blocks if len(b) > _BLOCK_TYPE and b[_BLOCK_TYPE] == _TEXT_BLOCK]

    # Sort top-to-bottom, then left-to-right. Without this, blocks come back in
    # the order the PDF happens to draw them, which is not reading order -- a
    # two-column layout would emit the whole right column before the left.
    #
    # KNOWN LIMIT: this operates on blocks, and PyMuPDF merges text that shares
    # a baseline into a SINGLE block even when it is visually in separate
    # columns. Within such a block the original draw order survives. Fixing
    # that needs word-level extraction, which would mean reconstructing
    # paragraphs from y-gaps by hand and risking the paragraph structure this
    # app depends on. Multi-row columns -- the realistic case -- sort correctly.
    text_blocks.sort(key=lambda b: (round(b[_Y0], 1), round(b[_X0], 1)))

    parts = []
    for block in text_blocks:
        chunk = (block[_TEXT] or "").strip()
        if chunk:
            parts.append(chunk)

    # Blank line between blocks preserves paragraph separation.
    return "\n\n".join(parts)


def _normalise(text: str) -> str:
    """Clean up extraction artefacts while preserving paragraph structure."""
    if not text:
        return ""

    # PDFs encode "fi"/"fl" as single ligature glyphs.
    for ligature, replacement in (
        ("ﬀ", "ff"), ("ﬁ", "fi"), ("ﬂ", "fl"),
        ("ﬃ", "ffi"), ("ﬄ", "ffl"),
    ):
        text = text.replace(ligature, replacement)

    # Curly quotes, dashes and non-breaking spaces -> plain equivalents, so the
    # analyser downstream sees one canonical form of each character.
    for fancy, plain in (
        ("‘", "'"), ("’", "'"), ("“", '"'), ("”", '"'),
        ("–", "-"), ("—", "-"), (" ", " "),
    ):
        text = text.replace(fancy, plain)

    # Words hyphenated across a line break: "engage-\nment" -> "engagement".
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)

    # Collapse runs of spaces/tabs, but never newlines.
    text = re.sub(r"[ \t]+", " ", text)
    # Three or more newlines collapse to one blank line.
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Trim trailing spaces on each line.
    text = re.sub(r"[ \t]+\n", "\n", text)

    return text.strip()
