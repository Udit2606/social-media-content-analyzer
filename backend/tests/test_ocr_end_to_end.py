"""Real Tesseract, no mocking.

Every other OCR test substitutes the engine so the suite runs on a machine
without it. These exercise the genuine pipeline:

    image bytes -> Pillow preprocessing -> Tesseract -> text -> JSON response

They are skipped only when the binary is genuinely absent, which is an
environment fact, not a way of hiding a failure. Where the engine IS present
they run and must pass.
"""

import pytest

from app.services import file_service, ocr_service

requires_tesseract = pytest.mark.skipif(
    not ocr_service.is_available(),
    reason="Tesseract binary not installed in this environment",
)


@requires_tesseract
class TestBinaryResolution:
    def test_engine_is_reachable(self):
        assert ocr_service.is_available() is True
        assert ocr_service.get_version() is not None

    def test_health_endpoint_reports_it(self, client):
        body = client.get("/api/health").json()
        assert body["tesseractAvailable"] is True
        assert body["tesseractVersion"]


@requires_tesseract
class TestRealImageOcr:
    def test_reads_text_from_a_clean_image(self, text_image):
        text, confidence = ocr_service.extract_text(text_image, "post.png")

        assert "Hello from an image" in text
        assert "Second line of text" in text
        assert confidence is not None and confidence > 60

    def test_preserves_line_structure(self, text_image):
        """Line breaks are signal for a social post, not decoration."""
        text, _ = ocr_service.extract_text(text_image, "post.png")
        assert "\n" in text.strip()

    def test_recovers_text_from_a_transparent_png(self, transparent_png):
        """Without alpha flattening this is black-on-black and yields nothing.
        This is the test that proves _preprocess earns its place."""
        text, _ = ocr_service.extract_text(transparent_png, "t.png")
        assert text.strip() != ""
        assert "transparent" in text.lower()

    def test_blank_image_yields_no_text(self, blank_image):
        text, _ = ocr_service.extract_text(blank_image, "blank.png")
        assert text.strip() == ""

    def test_poor_quality_image_degrades_without_crashing(self, poor_quality_image):
        """Tiny, low-contrast, heavily compressed. Recognition may well fail;
        what matters is that it fails as an empty/low-confidence result rather
        than an exception."""
        text, confidence = ocr_service.extract_text(poor_quality_image, "bad.jpg")

        assert isinstance(text, str)
        if confidence is not None:
            assert 0 <= confidence <= 100


@requires_tesseract
class TestRealApiRoundTrip:
    def test_png_upload_returns_extracted_text(self, client, text_image):
        response = client.post(
            "/api/upload", files={"file": ("post.png", text_image, "image/png")}
        )
        assert response.status_code == 200

        body = response.json()
        assert body["success"] is True
        assert body["file"]["kind"] == "image"
        assert body["extraction"]["method"] == "ocr_image"
        assert body["extraction"]["pageCount"] is None
        assert body["processing"]["engine"] == "Tesseract OCR"
        assert "Hello from an image" in body["extraction"]["text"]

    def test_confidence_is_reported_for_ocr(self, client, text_image):
        body = client.post(
            "/api/upload", files={"file": ("post.png", text_image, "image/png")}
        ).json()
        confidence = body["extraction"]["confidence"]
        assert confidence is not None
        assert 0 < confidence <= 100

    def test_counts_match_the_returned_text(self, client, text_image):
        body = client.post(
            "/api/upload", files={"file": ("post.png", text_image, "image/png")}
        ).json()
        extraction = body["extraction"]
        assert extraction["wordCount"] == len(extraction["text"].split())
        assert extraction["characterCount"] == len(extraction["text"])

    def test_blank_image_returns_no_text_found(self, client, blank_image):
        response = client.post(
            "/api/upload", files={"file": ("blank.png", blank_image, "image/png")}
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "NO_TEXT_FOUND"


@requires_tesseract
class TestRealScannedPdfFallback:
    def test_scanned_pdf_is_recovered_by_ocr(self, client, scanned_pdf):
        """The full fallback, for real: a PDF with zero text objects is
        rasterised and read by OCR instead of being reported as empty."""
        response = client.post(
            "/api/upload", files={"file": ("scan.pdf", scanned_pdf, "application/pdf")}
        )
        assert response.status_code == 200

        body = response.json()
        assert body["extraction"]["method"] == "ocr_pdf_fallback"
        assert body["extraction"]["pageCount"] == 1
        assert body["extraction"]["confidence"] is not None
        assert "SCANNED" in body["extraction"]["text"].upper()

    def test_digital_pdf_still_uses_native_extraction(self, client, digital_pdf):
        """Guards against the fallback firing when it should not."""
        body = client.post(
            "/api/upload", files={"file": ("d.pdf", digital_pdf, "application/pdf")}
        ).json()
        assert body["extraction"]["method"] == "pdf_text"
        assert body["extraction"]["confidence"] is None


@requires_tesseract
class TestServiceLevelRouting:
    def test_multipage_scan_ocrs_every_page(self, client):
        """Multi-page scanned PDFs must not stop after page one."""
        import fitz
        from tests.conftest import text_image_bytes

        # Word markers, not digits. Tesseract legitimately confuses 0/O and
        # 1/l, and this test is about page COVERAGE, not glyph accuracy --
        # a digit misread would fail it for an unrelated reason.
        markers = ["ALPHA", "BRAVO", "CHARLIE"]

        doc = fitz.open()
        for marker in markers:
            page = doc.new_page(width=800, height=300)
            page.insert_image(
                fitz.Rect(0, 0, 800, 300),
                stream=text_image_bytes([f"PAGE {marker}"], size=(1600, 300)),
            )
        data = doc.tobytes()
        doc.close()

        body = client.post(
            "/api/upload", files={"file": ("multi.pdf", data, "application/pdf")}
        ).json()

        assert body["extraction"]["method"] == "ocr_pdf_fallback"
        assert body["extraction"]["pageCount"] == 3

        text = body["extraction"]["text"].upper()
        for marker in markers:
            assert marker in text, f"page {marker} missing from OCR output"

        # Pages must also come back in document order.
        positions = [text.index(marker) for marker in markers]
        assert positions == sorted(positions), "pages were OCR'd out of order"
