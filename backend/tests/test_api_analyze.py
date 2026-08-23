"""POST /api/analyze: the combined extraction + AI pipeline, over real HTTP.

Every test here mocks analysis_service.analyze_text -- the network boundary --
so the suite runs without a Gemini key. The real network path is exercised
separately in test_ai_end_to_end.py, gated on a key actually being present.
"""

import json

import pytest

from app.schemas.ai_analysis import AIAnalysisResult
from app.services import analysis_service, ocr_service, text_metrics

VALID_AI_JSON = {
    "overall_score": 72,
    "scores": {
        "hook": 60, "clarity": 80, "call_to_action": 20,
        "readability": 75, "emotional_appeal": 55,
        "audience_relevance": 70, "hashtag_quality": 50,
    },
    "tone": {"label": "Confident", "descriptors": ["confident", "direct"]},
    "sentiment": {"label": "positive", "score": 0.3},
    "audience": {
        "primary": "Software engineers",
        "segments": ["backend engineers"],
        "reading_level": "Professional / technical",
    },
    "strengths": [{"title": "Clear structure", "detail": "Short paragraphs, easy to scan."}],
    "weaknesses": [
        {"title": "Weak close", "detail": "Ends flatly.", "severity": "medium"}
    ],
    "suggestions": [
        {"title": "Add a question", "detail": "Invite a reply.", "severity": "high", "example": None}
    ],
}


def _mock_analyze_success(monkeypatch):
    async def fake(text):
        result = AIAnalysisResult.model_validate(VALID_AI_JSON)
        # Real metrics, computed from the actual text the route received --
        # exercises the genuine deterministic path even though the AI call
        # itself is mocked.
        metrics = text_metrics.compute_metrics(text)
        return analysis_service._to_public_schema(result, metrics)

    monkeypatch.setattr(analysis_service, "analyze_text", fake)


class TestSuccessPath:
    def test_returns_extraction_and_analysis_together(self, client, digital_pdf, monkeypatch):
        _mock_analyze_success(monkeypatch)

        response = client.post(
            "/api/analyze", files={"file": ("post.pdf", digital_pdf, "application/pdf")}
        )
        assert response.status_code == 200

        body = response.json()
        assert body["success"] is True
        assert body["file"]["kind"] == "pdf"
        assert body["extraction"]["method"] == "pdf_text"
        assert body["analysis"]["overallScore"] == 72
        assert body["analysis"]["scores"]["callToAction"] == 20

    def test_response_shape_matches_documented_contract(self, client, digital_pdf, monkeypatch):
        _mock_analyze_success(monkeypatch)

        body = client.post(
            "/api/analyze", files={"file": ("post.pdf", digital_pdf, "application/pdf")}
        ).json()

        assert set(body) == {"success", "file", "extraction", "analysis", "processing"}
        analysis = body["analysis"]
        assert set(analysis) == {
            "overallScore", "scores", "tone", "sentiment", "audience",
            "strengths", "weaknesses", "suggestions", "metrics",
        }
        assert set(analysis["audience"]) == {"primary", "segments", "readingLevel"}
        assert set(analysis["scores"]) == {
            "hook", "clarity", "callToAction", "readability",
            "emotionalAppeal", "audienceRelevance", "hashtagQuality",
        }
        assert set(analysis["metrics"]) == {
            "characterCount", "wordCount", "sentenceCount",
            "avgWordsPerSentence", "readingTimeSeconds",
            "readabilityScore", "readabilityLevel",
        }

    def test_findings_have_stable_ids_for_react_keys(self, client, digital_pdf, monkeypatch):
        _mock_analyze_success(monkeypatch)

        body = client.post(
            "/api/analyze", files={"file": ("post.pdf", digital_pdf, "application/pdf")}
        ).json()

        assert body["analysis"]["strengths"][0]["id"] == "strength-1"
        assert body["analysis"]["weaknesses"][0]["id"] == "weakness-1"
        assert body["analysis"]["suggestions"][0]["id"] == "suggestion-1"

    def test_works_for_images_too(self, client, text_image, monkeypatch):
        monkeypatch.setattr(ocr_service, "is_available", lambda: True)
        monkeypatch.setattr(ocr_service, "extract_text", lambda c, f: ("hello world", 90.0))
        _mock_analyze_success(monkeypatch)

        response = client.post(
            "/api/analyze", files={"file": ("a.png", text_image, "image/png")}
        )
        assert response.status_code == 200
        assert response.json()["file"]["kind"] == "image"


class TestExtractionFailsBeforeAiIsCalled:
    """The AI must never be invoked -- and never billed -- for a file that
    fails extraction. This is the most important cost/correctness guarantee
    of the combined endpoint."""

    def _assert_ai_not_called(self, monkeypatch):
        async def explode(text):
            raise AssertionError("AI must not be called when extraction fails")

        monkeypatch.setattr(analysis_service, "analyze_text", explode)

    def test_unsupported_file_type(self, client, monkeypatch):
        self._assert_ai_not_called(monkeypatch)
        response = client.post(
            "/api/analyze", files={"file": ("notes.txt", b"plain text", "text/plain")}
        )
        assert response.status_code == 415
        assert response.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"

    def test_empty_file(self, client, monkeypatch):
        self._assert_ai_not_called(monkeypatch)
        response = client.post(
            "/api/analyze", files={"file": ("empty.pdf", b"", "application/pdf")}
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "EMPTY_FILE"

    def test_encrypted_pdf(self, client, encrypted_pdf, monkeypatch):
        self._assert_ai_not_called(monkeypatch)
        response = client.post(
            "/api/analyze", files={"file": ("locked.pdf", encrypted_pdf, "application/pdf")}
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "PASSWORD_PROTECTED"

    def test_blank_pdf_with_ocr_unavailable(self, client, blank_pdf, monkeypatch):
        monkeypatch.setattr(ocr_service, "is_available", lambda: False)
        self._assert_ai_not_called(monkeypatch)
        response = client.post(
            "/api/analyze", files={"file": ("blank.pdf", blank_pdf, "application/pdf")}
        )
        assert response.status_code in (422, 503)


class TestAiFailurePaths:
    def test_no_api_key_configured(self, client, digital_pdf, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "gemini_api_key", "")

        response = client.post(
            "/api/analyze", files={"file": ("post.pdf", digital_pdf, "application/pdf")}
        )
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "AI_UNAVAILABLE"

    def test_ai_network_failure_returns_503_not_500(self, client, digital_pdf, monkeypatch):
        from app.utils.errors import ai_unavailable

        async def fail(text):
            raise ai_unavailable()

        monkeypatch.setattr(analysis_service, "analyze_text", fail)

        response = client.post(
            "/api/analyze", files={"file": ("post.pdf", digital_pdf, "application/pdf")}
        )
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "AI_UNAVAILABLE"

    def test_ai_invalid_response_returns_502(self, client, digital_pdf, monkeypatch):
        from app.utils.errors import ai_response_invalid

        async def fail(text):
            raise ai_response_invalid()

        monkeypatch.setattr(analysis_service, "analyze_text", fail)

        response = client.post(
            "/api/analyze", files={"file": ("post.pdf", digital_pdf, "application/pdf")}
        )
        assert response.status_code == 502
        assert response.json()["error"]["code"] == "AI_RESPONSE_INVALID"

    def test_error_envelope_matches_every_other_endpoint(self, client, digital_pdf, monkeypatch):
        from app.utils.errors import ai_unavailable

        async def fail(text):
            raise ai_unavailable()

        monkeypatch.setattr(analysis_service, "analyze_text", fail)

        body = client.post(
            "/api/analyze", files={"file": ("post.pdf", digital_pdf, "application/pdf")}
        ).json()
        assert body["success"] is False
        assert set(body["error"]) <= {"code", "message", "hint"}


class TestHealthReportsAiStatus:
    def test_reports_unavailable_with_no_key(self, client, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "gemini_api_key", "")
        body = client.get("/api/health").json()
        assert body["aiAvailable"] is False
        assert body["aiModel"] is None

    def test_reports_available_and_model_with_a_key(self, client, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "gemini_api_key", "fake-key-for-testing")
        body = client.get("/api/health").json()
        assert body["aiAvailable"] is True
        assert body["aiModel"] == settings.gemini_model


class TestKeyNeverLeaks:
    """The one non-negotiable security property of this whole layer."""

    def test_key_absent_from_health_response(self, client, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "gemini_api_key", "super-secret-key-value")
        body = client.get("/api/health")
        assert "super-secret-key-value" not in body.text

    def test_key_absent_from_every_analyze_response(self, client, digital_pdf, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "gemini_api_key", "super-secret-key-value")
        _mock_analyze_success(monkeypatch)

        body = client.post(
            "/api/analyze", files={"file": ("post.pdf", digital_pdf, "application/pdf")}
        )
        assert "super-secret-key-value" not in body.text

    def test_key_absent_from_error_responses(self, client, digital_pdf, monkeypatch):
        from app.config import settings
        from app.utils.errors import ai_unavailable

        monkeypatch.setattr(settings, "gemini_api_key", "super-secret-key-value")

        async def fail(text):
            raise ai_unavailable()

        monkeypatch.setattr(analysis_service, "analyze_text", fail)

        body = client.post(
            "/api/analyze", files={"file": ("post.pdf", digital_pdf, "application/pdf")}
        )
        assert "super-secret-key-value" not in body.text

    def test_key_never_appears_in_the_openapi_schema(self, client, monkeypatch):
        """/docs and /openapi.json are public. A key embedded in a default
        value or example would be exposed to anyone who loads the docs page."""
        from app.config import settings

        monkeypatch.setattr(settings, "gemini_api_key", "super-secret-key-value")
        body = client.get("/openapi.json")
        assert "super-secret-key-value" not in body.text


@pytest.fixture
def anyio_backend():
    return "asyncio"


class TestAnalyzeTextRoute:
    """POST /api/analyze-text -- the two-step counterpart used by the frontend,
    which extracts via /api/upload first and then analyses the text it holds."""

    def test_analyses_supplied_text(self, client, monkeypatch):
        _mock_analyze_success(monkeypatch)

        response = client.post("/api/analyze-text", json={"text": "We shipped a thing."})
        assert response.status_code == 200

        body = response.json()
        assert body["success"] is True
        assert body["analysis"]["overallScore"] == 72
        # Extraction fields belong to /api/upload; this route returns analysis only.
        assert "extraction" not in body
        assert "file" not in body

    def test_metrics_are_computed_from_the_real_text_over_http(self, client, monkeypatch):
        """End-to-end proof that the deterministic path actually runs, not
        just that a `metrics` key exists somewhere in the JSON."""
        _mock_analyze_success(monkeypatch)

        response = client.post(
            "/api/analyze-text",
            json={"text": "One word. Two words here."},
        )
        metrics = response.json()["analysis"]["metrics"]

        assert metrics["wordCount"] == 5
        assert metrics["sentenceCount"] == 2
        assert metrics["characterCount"] == len("One word. Two words here.")
        assert 0 <= metrics["readabilityScore"] <= 100
        assert metrics["readabilityLevel"]

    def test_passes_the_text_through_unchanged(self, client, monkeypatch):
        received = {}

        async def fake(text):
            received["text"] = text
            result = AIAnalysisResult.model_validate(VALID_AI_JSON)
            return analysis_service._to_public_schema(result, text_metrics.compute_metrics(text))

        monkeypatch.setattr(analysis_service, "analyze_text", fake)

        client.post("/api/analyze-text", json={"text": "exact text here"})
        assert received["text"] == "exact text here"

    def test_rejects_missing_text(self, client):
        response = client.post("/api/analyze-text", json={})
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "BAD_REQUEST"

    def test_rejects_empty_text(self, client):
        response = client.post("/api/analyze-text", json={"text": ""})
        assert response.status_code == 400

    def test_ai_unavailable_returns_503(self, client, monkeypatch):
        from app.utils.errors import ai_unavailable

        async def fail(text):
            raise ai_unavailable()

        monkeypatch.setattr(analysis_service, "analyze_text", fail)

        response = client.post("/api/analyze-text", json={"text": "some post"})
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "AI_UNAVAILABLE"

    def test_does_not_run_extraction(self, client, monkeypatch):
        """This route must never touch the PDF/OCR pipeline -- that is the
        whole point of having it separate from /api/analyze."""
        from app.services import file_service

        async def explode(*args, **kwargs):
            raise AssertionError("extraction must not run for /api/analyze-text")

        monkeypatch.setattr(file_service, "process_upload", explode)
        _mock_analyze_success(monkeypatch)

        response = client.post("/api/analyze-text", json={"text": "some post"})
        assert response.status_code == 200
