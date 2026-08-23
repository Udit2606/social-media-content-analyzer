"""Server-side upload validation.

The browser also validates, but nothing it reports can be trusted: the
filename, the extension and the Content-Type header are all attacker
controlled. This module is the real gate.

It answers three questions, in order:
  1. Is the file small enough?   (checked while streaming, before buffering)
  2. Is it actually empty?
  3. What IS it, really?         (decided by magic bytes, not by name)
"""

import os
from typing import Optional, Tuple

from fastapi import UploadFile

from app.config import settings
from app.utils import errors

# Read the upload in chunks so a hostile 2 GB body is rejected after ~10 MB
# rather than being buffered into memory first.
_CHUNK_SIZE = 64 * 1024

# File signatures ("magic bytes"). A real PDF starts with "%PDF-", a PNG with a
# fixed 8-byte header, a JPEG with 0xFFD8FF. An attacker can rename anything to
# .pdf; they cannot fake the bytes without the file genuinely being that type.
_PDF_MAGIC = b"%PDF-"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8\xff"

# Human-readable list used in error copy, kept in one place.
ACCEPTED_LABEL = "PDF, PNG or JPG"


def sanitize_filename(raw: Optional[str]) -> str:
    """Strip any directory component from a client-supplied filename.

    A client can send "../../etc/passwd" as the filename. We never write
    uploads to disk, but the name is echoed back in the response and written to
    logs, so it is reduced to a bare basename regardless.
    """
    if not raw:
        return "upload"
    # Handle both POSIX and Windows separators before taking the basename.
    cleaned = raw.replace("\\", "/")
    base = os.path.basename(cleaned).strip()
    return base or "upload"


async def read_upload_within_limit(upload: UploadFile, filename: str) -> bytes:
    """Stream the upload into memory, aborting if it exceeds the size limit.

    Returns the raw bytes. Raises AppError for empty or oversized files.
    """
    limit = settings.max_file_size_bytes
    chunks = []
    total = 0

    while True:
        chunk = await upload.read(_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            # Stop reading immediately; do not buffer the rest of the body.
            raise errors.file_too_large(
                filename=filename,
                limit_mb=settings.max_file_size_mb,
            )
        chunks.append(chunk)

    if total == 0:
        raise errors.empty_file(filename)

    return b"".join(chunks)


def detect_file_kind(content: bytes, filename: str) -> Tuple[str, str]:
    """Identify the file from its content.

    Returns (kind, mime_type) where kind is "pdf" or "image".
    Raises AppError if the bytes do not match a supported format.

    Note this deliberately ignores both the extension and the Content-Type
    header the client sent. Only the bytes decide.
    """
    if content.startswith(_PDF_MAGIC):
        return "pdf", "application/pdf"
    if content.startswith(_PNG_MAGIC):
        return "image", "image/png"
    if content.startswith(_JPEG_MAGIC):
        return "image", "image/jpeg"

    raise errors.unsupported_file_type(filename, ACCEPTED_LABEL)
