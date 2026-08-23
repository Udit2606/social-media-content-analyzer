"""OCR pipeline.

The Tesseract binary is not required for most of these. Recognition accuracy
needs the real engine, but everything around it -- image preparation, parsing
Tesseract's tabular output, confidence maths, and failure handling -- is pure
logic and is tested here with synthetic engine output.
"""

import io

import pytest
from PIL import Image

from app.services import ocr_service
from app.utils.errors import AppError, ErrorCode


def _tesseract_output(words, confs, blocks=None, pars=None, lines=None):
    """Build a dict shaped like pytesseract.image_to_data(Output.DICT)."""
    count = len(words)
    return {
        "text": words,
        "conf": confs,
        "block_num": blocks if blocks is not None else [1] * count,
        "par_num": pars if pars is not None else [1] * count,
        "line_num": lines if lines is not None else [1] * count,
    }


class TestPreprocessing:
    def test_converts_to_greyscale(self, text_image):
        prepared = ocr_service._preprocess(Image.open(io.BytesIO(text_image)))
        assert prepared.mode == "L"

    def test_upscales_small_images(self, poor_quality_image):
        """Tesseract degrades badly below ~300px; small input must be enlarged."""
        original = Image.open(io.BytesIO(poor_quality_image))
        assert original.width < 1000

        prepared = ocr_service._preprocess(original)
        assert prepared.width >= 1000

    def test_does_not_downscale_large_images(self, text_image):
        original = Image.open(io.BytesIO(text_image))
        prepared = ocr_service._preprocess(original)
        assert prepared.width == original.width

    def test_flattens_transparency_onto_white(self, transparent_png):
        """Black text on a transparent background becomes black-on-black if
        alpha is dropped rather than composited onto white."""
        prepared = ocr_service._preprocess(Image.open(io.BytesIO(transparent_png)))

        pixels = list(prepared.getdata())
        assert max(pixels) > 200, "background should be near-white after flattening"
        assert min(pixels) < 100, "text should remain dark"

    def test_preserves_aspect_ratio_when_upscaling(self):
        source = Image.new("RGB", (200, 100), "white")
        prepared = ocr_service._preprocess(source)
        assert abs((prepared.width / prepared.height) - 2.0) < 0.05


class TestOutputAssembly:
    def test_joins_words_on_one_line(self):
        data = _tesseract_output(["Hello", "from", "an", "image"], [96, 95, 94, 93])
        text, confidence = ocr_service._assemble(data)
        assert text == "Hello from an image"
        assert confidence == pytest.approx(94.5, abs=0.1)

    def test_separates_lines_within_a_paragraph(self):
        data = _tesseract_output(
            ["first", "line", "second", "line"], [90] * 4, lines=[1, 1, 2, 2]
        )
        text, _ = ocr_service._assemble(data)
        assert text == "first line\nsecond line"

    def test_separates_paragraphs_with_a_blank_line(self):
        data = _tesseract_output(
            ["para", "one", "para", "two"], [90] * 4,
            pars=[1, 1, 2, 2], lines=[1, 1, 1, 1],
        )
        text, _ = ocr_service._assemble(data)
        assert text == "para one\n\npara two"

    def test_ignores_blank_word_entries(self):
        """Tesseract emits empty rows for layout gaps; they are not text."""
        data = _tesseract_output(["real", "", "   ", "words"], [90, -1, -1, 92])
        text, _ = ocr_service._assemble(data)
        assert text == "real words"

    def test_excludes_unscored_words_from_confidence(self):
        """Tesseract uses -1 for entries it did not score."""
        data = _tesseract_output(["a", "b"], [-1, 80])
        _, confidence = ocr_service._assemble(data)
        assert confidence == 80.0

    def test_confidence_is_none_when_nothing_was_scored(self):
        data = _tesseract_output(["a"], [-1])
        _, confidence = ocr_service._assemble(data)
        assert confidence is None

    def test_empty_output_yields_empty_text(self):
        text, confidence = ocr_service._assemble(_tesseract_output([], []))
        assert text == ""
        assert confidence is None

    def test_survives_missing_positional_columns(self):
        """Defensive: older or unusual Tesseract builds may omit columns.

        A truncated positional array must not raise IndexError mid-request.
        """
        data = {"text": ["a", "b", "c"], "conf": [90, 90, 90]}
        text, _ = ocr_service._assemble(data)
        assert "a" in text and "c" in text

    def test_survives_non_numeric_confidence(self):
        data = _tesseract_output(["a", "b"], ["not-a-number", 88])
        _, confidence = ocr_service._assemble(data)
        assert confidence == 88.0


class TestAvailability:
    def test_reports_unavailable_when_binary_is_missing(self, monkeypatch):
        monkeypatch.setattr(ocr_service, "is_available", lambda: False)
        with pytest.raises(AppError) as exc:
            ocr_service.extract_text(b"\x89PNG\r\n\x1a\n", "x.png")
        assert exc.value.code == ErrorCode.OCR_UNAVAILABLE
        assert exc.value.status_code == 503

    def test_version_probe_never_raises(self):
        """Used by /api/health, which must answer even with no engine."""
        assert ocr_service.get_version() is None or isinstance(
            ocr_service.get_version(), str
        )

    def test_availability_probe_never_raises(self):
        assert isinstance(ocr_service.is_available(), bool)


class TestImageDecoding:
    def test_rejects_undecodable_bytes(self):
        with pytest.raises(AppError) as exc:
            ocr_service._load_image(b"\x89PNG\r\n\x1a\nnot really a png", "x.png")
        assert exc.value.code == ErrorCode.CORRUPTED_FILE

    def test_decodes_a_valid_png(self, text_image):
        image = ocr_service._load_image(text_image, "x.png")
        assert image.width > 0 and image.height > 0
        assert image.format == "PNG"

    def test_decompression_bomb_limit_is_set(self):
        """Pillow will happily expand a small file into gigabytes without this."""
        assert Image.MAX_IMAGE_PIXELS is not None
        assert Image.MAX_IMAGE_PIXELS <= 100_000_000


class TestBinaryResolution:
    """How the service decides where Tesseract lives.

    Order of precedence: explicit env var, then PATH, then a short list of
    standard install locations. A machine-specific path must never be the
    primary mechanism.
    """

    def test_explicit_env_var_wins(self, monkeypatch, tmp_path):
        from app.config import settings

        fake = tmp_path / "tesseract"
        fake.write_text("#!/bin/sh\n")
        monkeypatch.setattr(settings, "tesseract_cmd", str(fake))

        assert ocr_service._resolve_tesseract_cmd() == str(fake)

    def test_falls_back_to_path_when_env_var_is_blank(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "tesseract_cmd", "")
        monkeypatch.setattr(
            ocr_service.shutil, "which", lambda name: "/somewhere/bin/tesseract"
        )
        assert ocr_service._resolve_tesseract_cmd() == "/somewhere/bin/tesseract"

    def test_bad_env_var_does_not_break_startup(self, monkeypatch):
        """A typo in TESSERACT_CMD must not stop the service booting; PDFs
        still work and images degrade to a clear 503."""
        from app.config import settings

        monkeypatch.setattr(settings, "tesseract_cmd", "/does/not/exist/tesseract")
        monkeypatch.setattr(
            ocr_service.shutil, "which", lambda name: "/usr/bin/tesseract"
        )
        assert ocr_service._resolve_tesseract_cmd() == "/usr/bin/tesseract"

    def test_probes_standard_locations_when_path_is_stripped(self, monkeypatch):
        """launchd and some supervisors start processes with a minimal PATH,
        so `tesseract` works in a terminal but not in the server process."""
        from app.config import settings

        monkeypatch.setattr(settings, "tesseract_cmd", "")
        monkeypatch.setattr(ocr_service.shutil, "which", lambda name: None)
        monkeypatch.setattr(
            ocr_service.os.path,
            "isfile",
            lambda p: p == "/opt/homebrew/bin/tesseract",
        )
        assert ocr_service._resolve_tesseract_cmd() == "/opt/homebrew/bin/tesseract"

    def test_degrades_to_plain_name_when_nothing_is_found(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "tesseract_cmd", "")
        monkeypatch.setattr(ocr_service.shutil, "which", lambda name: None)
        monkeypatch.setattr(ocr_service.os.path, "isfile", lambda p: False)

        assert ocr_service._resolve_tesseract_cmd() == "tesseract"

    def test_no_machine_specific_path_is_hardcoded_as_default(self):
        """The developer's own path may appear in the fallback LIST, but must
        never be what the code reaches for first."""
        import inspect

        source = inspect.getsource(ocr_service._resolve_tesseract_cmd)
        env_pos = source.index("settings.tesseract_cmd")
        path_pos = source.index('shutil.which("tesseract")')
        fallback_pos = source.index("_FALLBACK_PATHS")
        assert env_pos < path_pos < fallback_pos
