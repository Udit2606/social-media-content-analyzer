"""End-to-end API behaviour: contract, error consistency, cleanup, concurrency."""

import asyncio
import os
import tempfile
import time

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services import ocr_service


def post_file(client, name, content, content_type="application/octet-stream"):
    return client.post("/api/upload", files={"file": (name, content, content_type)})


class TestHealth:
    def test_returns_ok(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_reports_ocr_availability(self, client):
        """The most common deploy failure is a container without the binary.
        One request must answer whether OCR will work."""
        body = client.get("/api/health").json()
        assert "tesseractAvailable" in body
        assert isinstance(body["tesseractAvailable"], bool)

    def test_uses_camel_case(self, client):
        body = client.get("/api/health").json()
        assert "tesseract_available" not in body


class TestUploadContract:
    def test_digital_pdf_succeeds(self, client, digital_pdf):
        response = post_file(client, "post.pdf", digital_pdf, "application/pdf")
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_response_has_every_documented_field(self, client, digital_pdf):
        body = post_file(client, "post.pdf", digital_pdf, "application/pdf").json()

        assert set(body["file"]) == {"name", "kind", "sizeBytes", "mimeType"}
        assert set(body["extraction"]) == {
            "method", "text", "pageCount", "wordCount", "characterCount", "confidence",
        }
        assert set(body["processing"]) == {"durationMs", "engine", "notes"}

    def test_reports_pdf_metadata_correctly(self, client, digital_pdf):
        body = post_file(client, "post.pdf", digital_pdf, "application/pdf").json()

        assert body["file"]["kind"] == "pdf"
        assert body["file"]["mimeType"] == "application/pdf"
        assert body["file"]["sizeBytes"] == len(digital_pdf)
        assert body["extraction"]["method"] == "pdf_text"
        assert body["extraction"]["pageCount"] == 1
        assert body["extraction"]["confidence"] is None
        assert body["processing"]["engine"] == "PyMuPDF"

    def test_counts_match_the_returned_text(self, client, digital_pdf):
        body = post_file(client, "post.pdf", digital_pdf, "application/pdf").json()
        extraction = body["extraction"]

        assert extraction["wordCount"] == len(extraction["text"].split())
        assert extraction["characterCount"] == len(extraction["text"])

    def test_multipage_reports_page_count(self, client, multipage_pdf):
        body = post_file(client, "m.pdf", multipage_pdf, "application/pdf").json()
        assert body["extraction"]["pageCount"] == 3

    def test_strips_directory_components_from_filename(self, client, digital_pdf):
        """A client-supplied name is untrusted and is echoed back in the body."""
        body = post_file(
            client, "../../../etc/passwd.pdf", digital_pdf, "application/pdf"
        ).json()
        assert body["file"]["name"] == "passwd.pdf"
        assert "/" not in body["file"]["name"]


class TestValidationErrors:
    """Each case asserts BOTH the HTTP status and the machine-readable code,
    because the frontend branches on the code, not on the status."""

    @pytest.mark.parametrize(
        "name,content,status,code",
        [
            ("notes.txt", b"just plain text", 415, "UNSUPPORTED_FILE_TYPE"),
            ("fake.pdf", b"named .pdf but is not one", 415, "UNSUPPORTED_FILE_TYPE"),
            ("empty.pdf", b"", 400, "EMPTY_FILE"),
            ("broken.pdf", b"%PDF-1.4\ngarbage body", 422, "CORRUPTED_FILE"),
        ],
    )
    def test_rejects_bad_input(self, client, name, content, status, code):
        response = post_file(client, name, content)
        assert response.status_code == status
        assert response.json()["error"]["code"] == code

    def test_rejects_truncated_image(self, client):
        """A valid PNG signature with a garbage body must be reported as a
        damaged file, not as a server error."""
        response = post_file(client, "img.png", b"\x89PNG\r\n\x1a\ntruncated")
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "CORRUPTED_FILE"

    def test_rejects_oversized_upload(self, client):
        from app.config import settings

        payload = b"%PDF-1.4\n" + b"0" * (settings.max_file_size_bytes + 5000)
        response = post_file(client, "huge.pdf", payload, "application/pdf")
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "FILE_TOO_LARGE"

    def test_rejects_encrypted_pdf(self, client, encrypted_pdf):
        response = post_file(client, "locked.pdf", encrypted_pdf, "application/pdf")
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "PASSWORD_PROTECTED"

    def test_rejects_missing_file_field(self, client):
        response = client.post("/api/upload")
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "BAD_REQUEST"

    def test_rejects_wrong_field_name(self, client, digital_pdf):
        response = client.post(
            "/api/upload", files={"document": ("a.pdf", digital_pdf, "application/pdf")}
        )
        assert response.status_code == 400

    def test_content_type_header_cannot_bypass_type_detection(self, client):
        """Only the bytes decide. A lying Content-Type must not get through."""
        response = post_file(client, "evil.pdf", b"#!/bin/sh\nrm -rf /", "application/pdf")
        assert response.status_code == 415


class TestEmptyDocuments:
    def test_blank_pdf_without_ocr_is_not_a_500(self, client, blank_pdf, monkeypatch):
        """A structurally valid but contentless PDF is a user problem, not a
        server error. It must never surface as SERVER_ERROR."""
        monkeypatch.setattr(ocr_service, "is_available", lambda: False)
        response = post_file(client, "blank.pdf", blank_pdf, "application/pdf")

        assert response.status_code in (422, 503)
        assert response.json()["error"]["code"] in ("NO_TEXT_FOUND", "OCR_UNAVAILABLE")

    def test_image_with_no_text_reports_no_text_found(
        self, client, blank_image, monkeypatch
    ):
        monkeypatch.setattr(ocr_service, "is_available", lambda: True)
        monkeypatch.setattr(ocr_service, "extract_text", lambda c, f: ("", None))

        response = post_file(client, "blank.png", blank_image, "image/png")
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "NO_TEXT_FOUND"


class TestScannedPdfFallback:
    def test_routes_a_scan_through_ocr(self, client, scanned_pdf, monkeypatch):
        """The single most important behaviour: a scanned PDF has no text
        objects and would otherwise be reported as empty."""
        calls = {}

        def fake_ocr(images, filename):
            calls["pages"] = len(images)
            return "TEXT RECOVERED BY OCR", 88.5

        monkeypatch.setattr(ocr_service, "is_available", lambda: True)
        monkeypatch.setattr(ocr_service, "extract_text_from_images", fake_ocr)

        body = post_file(client, "scan.pdf", scanned_pdf, "application/pdf").json()

        assert calls["pages"] == 1, "pages should have been rasterised for OCR"
        assert body["extraction"]["method"] == "ocr_pdf_fallback"
        assert body["extraction"]["text"] == "TEXT RECOVERED BY OCR"
        assert body["extraction"]["confidence"] == 88.5
        assert body["processing"]["engine"] == "Tesseract OCR"

    def test_digital_pdf_never_touches_ocr(self, client, digital_pdf, monkeypatch):
        def explode(*args, **kwargs):
            raise AssertionError("OCR must not run for a PDF with real text")

        monkeypatch.setattr(ocr_service, "extract_text_from_images", explode)
        response = post_file(client, "d.pdf", digital_pdf, "application/pdf")
        assert response.json()["extraction"]["method"] == "pdf_text"


class TestImageUploads:
    def test_png_uses_ocr(self, client, text_image, monkeypatch):
        monkeypatch.setattr(ocr_service, "is_available", lambda: True)
        monkeypatch.setattr(ocr_service, "extract_text", lambda c, f: ("hello", 91.0))

        body = post_file(client, "a.png", text_image, "image/png").json()
        assert body["extraction"]["method"] == "ocr_image"
        assert body["extraction"]["pageCount"] is None
        assert body["extraction"]["confidence"] == 91.0
        assert body["file"]["kind"] == "image"

    def test_missing_engine_returns_503_not_500(self, client, text_image, monkeypatch):
        monkeypatch.setattr(ocr_service, "is_available", lambda: False)
        response = post_file(client, "a.png", text_image, "image/png")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "OCR_UNAVAILABLE"


class TestErrorEnvelopeConsistency:
    """Every failure, from any layer, must have the same shape. The frontend
    reads error.code and error.message and nothing else."""

    @pytest.mark.parametrize(
        "make_request",
        [
            lambda c: c.post("/api/upload", files={"file": ("a.txt", b"x", "text/plain")}),
            lambda c: c.post("/api/upload", files={"file": ("e.pdf", b"", "application/pdf")}),
            lambda c: c.post("/api/upload"),
            lambda c: c.post("/api/analyze"),
            lambda c: c.get("/api/does-not-exist"),
            lambda c: c.get("/"),
        ],
    )
    def test_shape_is_identical_for_every_failure(self, client, make_request):
        response = make_request(client)
        assert response.status_code >= 400

        body = response.json()
        assert body["success"] is False
        assert isinstance(body["error"]["code"], str) and body["error"]["code"]
        assert isinstance(body["error"]["message"], str) and body["error"]["message"]
        assert set(body["error"]) <= {"code", "message", "hint"}

    def test_messages_never_leak_internals(self, client, encrypted_pdf):
        response = post_file(client, "l.pdf", encrypted_pdf, "application/pdf")
        serialised = response.text.lower()
        for leak in ("traceback", "site-packages", "/users/", ".venv", "fitz."):
            assert leak not in serialised

    def test_unexpected_exception_becomes_a_clean_500(self, client, digital_pdf, monkeypatch):
        from app.services import pdf_service

        def boom(*args, **kwargs):
            raise RuntimeError("secret internal detail /Users/someone/app.py")

        monkeypatch.setattr(pdf_service, "extract_text", boom)

        with pytest.raises(RuntimeError):
            # TestClient re-raises by default; the handler is verified below.
            post_file(client, "d.pdf", digital_pdf, "application/pdf")

    def test_unexpected_exception_handler_hides_the_detail(self, digital_pdf, monkeypatch):
        from fastapi.testclient import TestClient
        from app.services import pdf_service

        def boom(*args, **kwargs):
            raise RuntimeError("secret internal detail /Users/someone/app.py")

        monkeypatch.setattr(pdf_service, "extract_text", boom)

        with TestClient(app, raise_server_exceptions=False) as safe_client:
            response = safe_client.post(
                "/api/upload", files={"file": ("d.pdf", digital_pdf, "application/pdf")}
            )
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "SERVER_ERROR"
        assert "secret internal detail" not in response.text
        assert "/Users/" not in response.text


class TestAnalyzeRequiresAFile:
    """/api/analyze is no longer a 501 stub -- it is the full extraction + AI
    pipeline, covered end-to-end in test_api_analyze.py. What belongs here is
    just the same "no file field" contract every upload-accepting route shares."""

    def test_rejects_a_request_with_no_file(self, client):
        response = client.post("/api/analyze")
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "BAD_REQUEST"


class TestTemporaryFileCleanup:
    def test_no_files_are_left_behind(self, client, digital_pdf, scanned_pdf, text_image):
        """The service processes entirely in memory. Nothing should ever appear
        in the system temp directory, so there is no cleanup to get wrong."""
        temp_dir = tempfile.gettempdir()
        before = set(os.listdir(temp_dir))

        post_file(client, "a.pdf", digital_pdf, "application/pdf")
        post_file(client, "b.pdf", scanned_pdf, "application/pdf")
        post_file(client, "c.png", text_image, "image/png")
        post_file(client, "d.txt", b"nope", "text/plain")

        after = set(os.listdir(temp_dir))
        leaked = {
            name for name in (after - before)
            if not name.startswith(("pytest-", ".", "com.apple"))
        }
        assert leaked == set(), f"left files in temp: {leaked}"


class TestConcurrency:
    @pytest.mark.anyio
    async def test_extraction_does_not_block_the_event_loop(self, monkeypatch):
        """CPU-bound extraction must run in a worker thread, not on the loop.

        OCR of a multi-page scan takes seconds. If that work runs inline in an
        async handler the whole process stops serving: health checks time out
        and every other user waits behind it.

        The check measures the event loop's own responsiveness. A blocked loop
        cannot honour a short asyncio.sleep, so the sleep overruns by however
        long the CPU work took. Measuring a second HTTP request instead would
        silently pass, because that request cannot even be *sent* until the
        loop is free again.
        """
        from app.services import pdf_service

        def slow_extract(content, filename):
            time.sleep(0.8)          # stands in for real OCR/parse cost
            return "done", 1

        monkeypatch.setattr(pdf_service, "extract_text", slow_extract)
        monkeypatch.setattr(pdf_service, "looks_scanned", lambda t, p: False)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            upload = asyncio.create_task(
                ac.post(
                    "/api/upload",
                    files={"file": ("a.pdf", b"%PDF-1.4\nx", "application/pdf")},
                )
            )

            # Timing starts before the first yield. Awaiting anything hands
            # control to the upload task, so if that task blocks, THIS sleep is
            # the one that overruns. Measuring a later sleep would silently
            # pass, because by then the blocking work has already finished.
            started = time.perf_counter()
            await asyncio.sleep(0.05)
            loop_stall = time.perf_counter() - started - 0.05

            response = await upload

        assert response.status_code == 200
        assert loop_stall < 0.3, (
            f"event loop stalled for {loop_stall:.2f}s during an upload: "
            "CPU-bound work is running on the loop instead of in a thread"
        )


@pytest.fixture
def anyio_backend():
    return "asyncio"
