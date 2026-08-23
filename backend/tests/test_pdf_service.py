"""PDF extraction: accuracy, structure, multi-page, scans, failure modes."""

import fitz
import pytest

from app.services import pdf_service
from app.utils.errors import AppError, ErrorCode


class TestExtractionAccuracy:
    def test_extracts_all_text_verbatim(self, digital_pdf):
        from tests.conftest import PARAGRAPH_ONE, PARAGRAPH_TWO, PARAGRAPH_THREE

        text, pages = pdf_service.extract_text(digital_pdf, "digital.pdf")

        assert pages == 1
        assert PARAGRAPH_ONE in text
        assert PARAGRAPH_TWO in text
        assert PARAGRAPH_THREE in text

    def test_preserves_paragraph_breaks(self, digital_pdf):
        """Line structure is signal, not decoration: a wall of text scores
        differently from a well-broken post, so it must survive extraction."""
        text, _ = pdf_service.extract_text(digital_pdf, "digital.pdf")
        assert "\n" in text

    def test_no_leading_or_trailing_whitespace(self, digital_pdf):
        text, _ = pdf_service.extract_text(digital_pdf, "digital.pdf")
        assert text == text.strip()

    def test_orders_multirow_columns_by_position_not_draw_order(self):
        """The realistic two-column case.

        The fixture draws the entire right column first. Correct reading order
        interleaves the columns row by row, left before right.
        """
        doc = fitz.open()
        page = doc.new_page(width=600, height=400)
        for index in range(4):
            page.insert_text((330, 100 + index * 24), f"right line {index}", fontsize=11)
        for index in range(4):
            page.insert_text((60, 100 + index * 24), f"left line {index}", fontsize=11)
        data = doc.tobytes()
        doc.close()

        text, _ = pdf_service.extract_text(data, "columns.pdf")
        assert text.index("left line 0") < text.index("right line 0")
        assert text.index("right line 0") < text.index("left line 1")

    @pytest.mark.xfail(
        reason=(
            "Known limitation: PyMuPDF merges text sharing a baseline into one "
            "block, and draw order survives inside a block. Documented in "
            "pdf_service._extract_page; would need word-level extraction."
        ),
        strict=True,
    )
    def test_same_baseline_columns_are_misordered(self, two_column_pdf):
        text, _ = pdf_service.extract_text(two_column_pdf, "columns.pdf")
        assert text.index("LEFT COLUMN") < text.index("RIGHT COLUMN")


class TestMultiPage:
    def test_reports_correct_page_count(self, multipage_pdf):
        _, pages = pdf_service.extract_text(multipage_pdf, "multi.pdf")
        assert pages == 3

    def test_includes_every_page(self, multipage_pdf):
        text, _ = pdf_service.extract_text(multipage_pdf, "multi.pdf")
        for index in (1, 2, 3):
            assert f"Page {index} heading" in text

    def test_pages_appear_in_order(self, multipage_pdf):
        text, _ = pdf_service.extract_text(multipage_pdf, "multi.pdf")
        assert text.index("Page 1") < text.index("Page 2") < text.index("Page 3")


class TestScannedDetection:
    def test_digital_pdf_is_not_flagged_as_scanned(self, digital_pdf):
        text, pages = pdf_service.extract_text(digital_pdf, "digital.pdf")
        assert pdf_service.looks_scanned(text, pages) is False

    def test_scanned_pdf_is_flagged(self, scanned_pdf):
        """The whole fallback hinges on this. A scan yields no text objects."""
        text, pages = pdf_service.extract_text(scanned_pdf, "scan.pdf")
        assert text.strip() == ""
        assert pdf_service.looks_scanned(text, pages) is True

    def test_blank_pdf_is_flagged(self, blank_pdf):
        text, pages = pdf_service.extract_text(blank_pdf, "blank.pdf")
        assert pdf_service.looks_scanned(text, pages) is True

    def test_zero_page_document_is_flagged(self):
        assert pdf_service.looks_scanned("", 0) is True


class TestRasterising:
    def test_renders_one_image_per_page(self, multipage_pdf):
        images = pdf_service.render_pages_to_images(multipage_pdf, "multi.pdf")
        assert len(images) == 3
        assert all(img.startswith(b"\x89PNG") for img in images)

    def test_respects_the_page_cap(self, monkeypatch):
        """A hostile 500-page upload must not be rendered in full."""
        from app.config import settings

        monkeypatch.setattr(settings, "max_ocr_pages", 2)

        doc = fitz.open()
        for _ in range(6):
            doc.new_page()
        data = doc.tobytes()
        doc.close()

        images = pdf_service.render_pages_to_images(data, "big.pdf")
        assert len(images) == 2


class TestFailureModes:
    def test_encrypted_pdf_raises_password_protected(self, encrypted_pdf):
        with pytest.raises(AppError) as exc:
            pdf_service.extract_text(encrypted_pdf, "locked.pdf")
        assert exc.value.code == ErrorCode.PASSWORD_PROTECTED
        assert exc.value.status_code == 422

    def test_corrupt_body_raises_corrupted_file(self):
        payload = b"%PDF-1.4\nthis header is a lie and the body is garbage"
        with pytest.raises(AppError) as exc:
            pdf_service.extract_text(payload, "broken.pdf")
        assert exc.value.code == ErrorCode.CORRUPTED_FILE

    def test_error_message_never_leaks_internals(self, encrypted_pdf):
        with pytest.raises(AppError) as exc:
            pdf_service.extract_text(encrypted_pdf, "locked.pdf")
        lowered = exc.value.message.lower()
        for leak in ("traceback", "/users/", "site-packages", ".py", "fitz"):
            assert leak not in lowered


class TestNormalisation:
    def test_joins_words_hyphenated_across_lines(self):
        assert "engagement" in pdf_service._normalise("engage-\nment")

    def test_expands_ligatures(self):
        assert pdf_service._normalise("ﬁrst ﬂow") == "first flow"

    def test_collapses_excess_blank_lines_but_keeps_one(self):
        assert pdf_service._normalise("a\n\n\n\n\nb") == "a\n\nb"

    def test_collapses_repeated_spaces(self):
        assert pdf_service._normalise("a      b") == "a b"

    def test_normalises_smart_punctuation(self):
        assert pdf_service._normalise("“hello” — it’s") == '"hello" - it\'s'

    def test_handles_empty_input(self):
        assert pdf_service._normalise("") == ""
