"""Shared fixtures: real documents built at test time, not committed binaries.

Generating fixtures in code means the tests are self-describing (you can see
exactly what text a PDF contains) and there are no opaque binaries in the repo.
"""

import io

import fitz
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont


def render_font(size: int):
    """A scalable font that does not depend on any system font being present.

    The default PIL bitmap font is far too small for reliable OCR -- it drops
    inter-word spaces -- so fixtures that are meant to be readable use this.
    """
    return ImageFont.load_default(size=size)


def text_image_bytes(lines, size=(1400, 340), font_size=44, fmt="PNG"):
    """Render lines of text onto a clean white canvas."""
    canvas = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(canvas)
    font = render_font(font_size)
    for index, line in enumerate(lines):
        draw.text((40, 50 + index * 110), line, fill="black", font=font)
    buffer = io.BytesIO()
    canvas.save(buffer, format=fmt)
    return buffer.getvalue()

from app.main import app

# Text used by the digital-PDF fixtures, so assertions can check exact content.
PARAGRAPH_ONE = "We just shipped our biggest update yet."
PARAGRAPH_TWO = "Latency is down 60% and there was zero downtime."
PARAGRAPH_THREE = "Huge credit to the whole team. #engineering"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def digital_pdf() -> bytes:
    """A one-page PDF containing real, selectable text objects."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), PARAGRAPH_ONE, fontsize=12)
    page.insert_text((72, 140), PARAGRAPH_TWO, fontsize=12)
    page.insert_text((72, 180), PARAGRAPH_THREE, fontsize=12)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def multipage_pdf() -> bytes:
    """Three pages, each with identifiable text, for page-ordering checks."""
    doc = fitz.open()
    for index in range(3):
        page = doc.new_page()
        page.insert_text((72, 100), f"Page {index + 1} heading", fontsize=14)
        page.insert_text((72, 140), f"Body text for page {index + 1}.", fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def two_column_pdf() -> bytes:
    """Two columns, to check blocks are ordered by position, not draw order.

    The right column is drawn FIRST so a naive extractor that trusts draw order
    would emit it before the left column.
    """
    doc = fitz.open()
    page = doc.new_page(width=600, height=400)
    page.insert_text((330, 100), "RIGHT COLUMN TEXT", fontsize=11)
    page.insert_text((60, 100), "LEFT COLUMN TEXT", fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def scanned_pdf() -> bytes:
    """A PDF whose only content is an image of text: zero text objects."""
    rendered = text_image_bytes(
        ["SCANNED DOCUMENT", "This text exists only as pixels"],
        size=(1600, 300),
    )

    doc = fitz.open()
    page = doc.new_page(width=800, height=300)
    page.insert_image(fitz.Rect(0, 0, 800, 300), stream=rendered)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def blank_pdf() -> bytes:
    """A structurally valid PDF with one page and no content at all."""
    doc = fitz.open()
    doc.new_page()
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def encrypted_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "classified", fontsize=12)
    data = doc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="hunter2")
    doc.close()
    return data


@pytest.fixture
def text_image() -> bytes:
    """A clean, high-contrast image of text."""
    return text_image_bytes(["Hello from an image", "Second line of text"])


@pytest.fixture
def poor_quality_image() -> bytes:
    """Tiny, low-contrast, noisy: the realistic worst case for OCR."""
    canvas = Image.new("RGB", (240, 70), (168, 168, 168))
    draw = ImageDraw.Draw(canvas)
    draw.text((6, 24), "faint text", fill=(140, 140, 140))
    buffer = io.BytesIO()
    canvas.save(buffer, format="JPEG", quality=18)
    return buffer.getvalue()


@pytest.fixture
def transparent_png() -> bytes:
    """Black text on a transparent background.

    If alpha is not flattened onto white before greyscale conversion, this
    becomes black-on-black and OCR returns nothing.
    """
    canvas = Image.new("RGBA", (1400, 200), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.text((40, 60), "transparent background", fill=(0, 0, 0, 255),
              font=render_font(44))
    buffer = io.BytesIO()
    canvas.save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def blank_image() -> bytes:
    canvas = Image.new("RGB", (900, 400), "white")
    buffer = io.BytesIO()
    canvas.save(buffer, format="PNG")
    return buffer.getvalue()
