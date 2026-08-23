"""Optical character recognition with Tesseract, via pytesseract.

An image has no text inside it -- only coloured pixels. OCR infers the
characters back out. Tesseract 4/5 does this with an LSTM that reads a whole
line as a sequence rather than matching letters in isolation, which is why it
copes with varied fonts.

Accuracy is dominated by the pre-processing step, not by the recogniser. A dim,
low-contrast, small photograph will OCR badly no matter what happens afterwards,
so this module converts to greyscale, upscales small images and boosts contrast
before handing anything to Tesseract.

IMPORTANT: pytesseract is only a thin wrapper. The actual Tesseract engine is a
separate compiled binary that must exist on the machine. `is_available()` exists
so a missing binary surfaces as a clear 503 and on the health endpoint, rather
than as an opaque crash on the first image upload.
"""

import io
import logging
import os
import shutil
from functools import lru_cache
from typing import List, Optional, Tuple

import pytesseract
from PIL import Image, ImageEnhance, ImageOps

from app.config import settings
from app.utils import errors

logger = logging.getLogger(__name__)

# Well-known install locations, probed only if the binary is not on PATH.
# These are fallbacks, not defaults: a machine-specific path must never be the
# primary mechanism, or the service stops being portable.
_FALLBACK_PATHS = (
    "/opt/homebrew/bin/tesseract",   # macOS, Apple Silicon Homebrew
    "/usr/local/bin/tesseract",      # macOS, Intel Homebrew
    "/opt/local/bin/tesseract",      # macOS, MacPorts
    "/usr/bin/tesseract",            # Debian/Ubuntu, most containers
)


def _resolve_tesseract_cmd() -> str:
    """Decide how to invoke Tesseract, in order of decreasing explicitness.

    1. TESSERACT_CMD, if set. An operator saying exactly where the binary is
       always wins, and is the only mechanism that works on an unusual host.
    2. Whatever is on PATH. This is the normal case on a developer machine and
       in any sanely built container, and needs no configuration at all.
    3. A short list of standard install locations, for the case where the
       process was started with a stripped PATH -- launchd, some supervisors
       and some CI runners do this, so `tesseract` works in your terminal but
       not in the server process.

    Returns the command to hand to pytesseract; "tesseract" means "use PATH".
    """
    configured = settings.tesseract_cmd.strip()
    if configured:
        if not os.path.isfile(configured):
            # Do not fail hard: is_available() will report False and image
            # uploads will 503 with a clear message. A typo in an env var
            # should not stop the service booting and serving PDFs.
            logger.warning(
                "TESSERACT_CMD is set to %r but no file exists there; "
                "falling back to PATH lookup.",
                configured,
            )
        else:
            return configured

    on_path = shutil.which("tesseract")
    if on_path:
        return on_path

    for candidate in _FALLBACK_PATHS:
        if os.path.isfile(candidate):
            logger.info(
                "tesseract is not on PATH; using known install location %s. "
                "Set TESSERACT_CMD to make this explicit.",
                candidate,
            )
            return candidate

    logger.warning(
        "Tesseract binary not found on PATH or in any standard location. "
        "Image uploads will return 503 until it is installed. "
        "Searched PATH=%r",
        os.environ.get("PATH", ""),
    )
    return "tesseract"


pytesseract.pytesseract.tesseract_cmd = _resolve_tesseract_cmd()

# Images narrower than this are upscaled; Tesseract struggles below ~300px.
_MIN_WIDTH = 1000

# Refuse absurd dimensions. Pillow will happily try to decompress a
# "decompression bomb" that expands to gigabytes in memory.
Image.MAX_IMAGE_PIXELS = 64_000_000  # ~64 megapixels


@lru_cache(maxsize=1)
def get_version() -> Optional[str]:
    """Probe the Tesseract binary once per process.

    Each call shells out to `tesseract --version`, and this runs on every
    health check and before every image upload. The answer cannot change
    without a redeploy, so it is cached. Installing Tesseract on an already
    running host therefore needs a restart to be picked up -- an acceptable
    trade for not spawning a subprocess on every request.
    """
    try:
        return str(pytesseract.get_tesseract_version())
    except Exception:
        return None


def is_available() -> bool:
    """True when the Tesseract binary can actually be invoked."""
    return get_version() is not None


def extract_text(content: bytes, filename: str) -> Tuple[str, Optional[float]]:
    """Run OCR over a single image held in memory.

    Returns (text, mean_confidence) where confidence is 0-100, or None when
    Tesseract reported no scored words.
    """
    if not is_available():
        raise errors.ocr_unavailable()

    image = _load_image(content, filename)
    prepared = _preprocess(image)
    return _run_ocr(prepared)


def extract_text_from_images(images: List[bytes], filename: str) -> Tuple[str, Optional[float]]:
    """Run OCR over several rendered pages and join the results.

    Used for the scanned-PDF fallback, where each page has been rasterised.
    """
    if not is_available():
        raise errors.ocr_unavailable()

    pages: List[str] = []
    confidences: List[float] = []

    for raw in images:
        image = _load_image(raw, filename)
        text, confidence = _run_ocr(_preprocess(image))
        if text.strip():
            pages.append(text.strip())
        if confidence is not None:
            confidences.append(confidence)

    mean_confidence = sum(confidences) / len(confidences) if confidences else None
    return "\n\n".join(pages), mean_confidence


# -- Internals -------------------------------------------------------------


def _load_image(content: bytes, filename: str) -> Image.Image:
    """Decode bytes into a Pillow image. Never writes to disk."""
    try:
        image = Image.open(io.BytesIO(content))
        # Force a full decode now so a truncated or malicious file fails here,
        # inside our try block, rather than later during processing.
        image.load()
        return image
    except Image.DecompressionBombError:
        logger.warning("Rejected oversized image", exc_info=True)
        raise errors.corrupted_file(filename)
    except Exception:
        logger.warning("Failed to decode image", exc_info=True)
        raise errors.corrupted_file(filename)


def _preprocess(image: Image.Image) -> Image.Image:
    """Greyscale, upscale and contrast-boost. This is where accuracy is won."""
    # Honour EXIF orientation, otherwise a phone photo may arrive rotated.
    image = ImageOps.exif_transpose(image)

    # Flatten transparency onto white; a transparent PNG otherwise becomes
    # black-on-black once converted to greyscale.
    if image.mode in ("RGBA", "LA", "P"):
        image = image.convert("RGBA")
        backdrop = Image.new("RGBA", image.size, (255, 255, 255, 255))
        image = Image.alpha_composite(backdrop, image)

    image = image.convert("L")

    if image.width < _MIN_WIDTH:
        scale = _MIN_WIDTH / image.width
        new_size = (_MIN_WIDTH, max(1, int(image.height * scale)))
        image = image.resize(new_size, Image.LANCZOS)

    # Modest contrast boost. Aggressive binarisation helps clean scans but
    # destroys detail in photographs, so this stays conservative.
    image = ImageEnhance.Contrast(image).enhance(1.6)

    return image


def _run_ocr(image: Image.Image) -> Tuple[str, Optional[float]]:
    """Invoke Tesseract and compute a mean word confidence."""
    try:
        data = pytesseract.image_to_data(
            image,
            lang=settings.ocr_language,
            output_type=pytesseract.Output.DICT,
        )
    except pytesseract.TesseractNotFoundError:
        raise errors.ocr_unavailable()
    except Exception:
        logger.error("Tesseract failed", exc_info=True)
        raise errors.AppError(
            code=errors.ErrorCode.SERVER_ERROR,
            message="Text recognition failed while reading that file.",
            status_code=500,
        )

    return _assemble(data)


def _at(data: dict, key: str, index: int, default: int = 0) -> int:
    """Read data[key][index] without assuming the column exists or is long enough.

    Tesseract normally returns every positional column at the same length as
    `text`, but a truncated or unusual build must not crash a request. A
    missing value collapses to a shared default, which merges affected words
    into one paragraph -- degraded grouping, never an exception.
    """
    try:
        return int(data[key][index])
    except (KeyError, IndexError, TypeError, ValueError):
        return default


def _assemble(data: dict) -> Tuple[str, Optional[float]]:
    """Rebuild lines and paragraphs from Tesseract's per-word output.

    image_to_data returns one row per word with block/paragraph/line indices.
    Grouping by those indices restores the line and paragraph breaks that
    image_to_string alone would flatten.
    """
    words = data.get("text", [])
    confidences = data.get("conf", [])

    # (block, paragraph, line) -> the words on that line, in reading order.
    lines: dict = {}
    scored: List[float] = []

    for index, word in enumerate(words):
        text = (word or "").strip()
        if not text:
            continue

        try:
            confidence = float(confidences[index])
        except (TypeError, ValueError, IndexError):
            confidence = -1.0

        # Tesseract uses -1 for entries it did not score.
        if confidence >= 0:
            scored.append(confidence)

        key = (
            _at(data, "block_num", index),
            _at(data, "par_num", index),
            _at(data, "line_num", index),
        )
        lines.setdefault(key, []).append(text)

    # Walk lines in order, starting a new paragraph whenever the
    # (block, paragraph) prefix changes.
    paragraphs: List[str] = []
    buffer: List[str] = []
    current_paragraph = None

    for key, line_words in sorted(lines.items()):
        paragraph_key = key[:2]
        if current_paragraph is not None and paragraph_key != current_paragraph:
            paragraphs.append("\n".join(buffer))
            buffer = []
        current_paragraph = paragraph_key
        buffer.append(" ".join(line_words))

    if buffer:
        paragraphs.append("\n".join(buffer))

    text = "\n\n".join(paragraphs)
    mean_confidence = round(sum(scored) / len(scored), 1) if scored else None

    return text.strip(), mean_confidence
