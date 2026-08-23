"""POST /api/improve: request validation, the combined pipeline, and error
handling, over real HTTP.

analysis_service is mocked at the network boundary (improvement_service._call_gemini),
same discipline as every other AI test in this project -- no Gemini key
required. A gated, real-network suite lives in test_ai_end_to_end.py, guarded
by the same skipif pattern already established there.
"""

import json

import pytest

from app.services import improvement_service

VALID_ANALYSIS_PAYLOAD = {
    "overallScore": 68,
    "scores": {
        "hook": 55, "clarity": 78, "callToAction": 10,
        "readability": 72, "emotionalAppeal": 60,
        "audienceRelevance": 65, "hashtagQuality": 50,
    },
    "tone": {"label": "Confident", "descriptors": ["confident"]},
    "sentiment": {"label": "positive", "score": 0.4},
    "audience": {
        "primary": "Software engineers",
        "segments": ["backend engineers"],
        "readingLevel": "Professional / technical",
    },
    "strengths": [{"id": "strength-1", "title": "Concrete numbers", "detail": "Cites 60%."}],
    "weaknesses": [
        {"id": "weakness-1", "title": "No closing ask", "detail": "Ends flatly.", "severity": "high"}
    ],
    "suggestions": [
        {
            "id": "suggestion-1", "title": "Add a CTA", "detail": "Close with a question.",
            "severity": "high", "example": None,
        }
    ],
    "metrics": {
        "characterCount": 62,
        "wordCount": 12,
        "sentenceCount": 2,
        "avgWordsPerSentence": 6.0,
        "readingTimeSeconds": 4,
        "readabilityScore": 70.0,
        "readabilityLevel": "Easy to read",
    },
}

VALID_AI_JSON = {
    "hook": "We cut latency by 60% -- with zero downtime.",
    "body": "Six months of work went into rebuilding the ingestion layer from scratch.",
    "cta": "What's the trickiest migration you've shipped?",
    "hashtags": ["engineering", "backend"],
    "full_post": "We cut latency by 60%.\n\nSix months of work.\n\nWhat's the trickiest migration you've shipped?",
}


def _mock_generation_success(monkeypatch):
    async def fake(prompt):
        return json.dumps(VALID_AI_JSON)

    monkeypatch.setattr(improvement_service, "_call_gemini", fake)


def _request_body(**overrides):
    body = {
        "content": "We just shipped our biggest update yet. Latency is down 60%.",
        "platform": "linkedin",
        "analysis": VALID_ANALYSIS_PAYLOAD,
    }
    body.update(overrides)
    return body


class TestSuccessPath:
    def test_returns_the_improved_post(self, client, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "gemini_api_key", "fake-key-for-testing")
        _mock_generation_success(monkeypatch)

        response = client.post("/api/improve", json=_request_body())
        assert response.status_code == 200

        body = response.json()
        assert body["success"] is True
        assert body["platform"] == "linkedin"
        assert body["improved"]["hook"] == VALID_AI_JSON["hook"]
        assert body["improved"]["hashtags"] == ["engineering", "backend"]

    def test_response_shape_matches_documented_contract(self, client, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "gemini_api_key", "fake-key-for-testing")
        _mock_generation_success(monkeypatch)

        body = client.post("/api/improve", json=_request_body()).json()

        assert set(body) == {"success", "platform", "improved"}
        assert set(body["improved"]) == {"hook", "body", "cta", "hashtags", "fullPost"}

    @pytest.mark.parametrize("platform", ["linkedin", "instagram", "x", "facebook"])
    def test_accepts_every_supported_platform(self, client, monkeypatch, platform):
        from app.config import settings

        monkeypatch.setattr(settings, "gemini_api_key", "fake-key-for-testing")
        _mock_generation_success(monkeypatch)

        response = client.post("/api/improve", json=_request_body(platform=platform))
        assert response.status_code == 200
        assert response.json()["platform"] == platform

    def test_accepts_an_optional_instruction(self, client, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "gemini_api_key", "fake-key-for-testing")

        received = {}

        async def fake(prompt):
            received["prompt"] = prompt
            return json.dumps(VALID_AI_JSON)

        monkeypatch.setattr(improvement_service, "_call_gemini", fake)

        response = client.post(
            "/api/improve", json=_request_body(instruction="make it punchier")
        )
        assert response.status_code == 200
        assert "make it punchier" in received["prompt"]

    def test_works_without_an_instruction(self, client, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "gemini_api_key", "fake-key-for-testing")
        _mock_generation_success(monkeypatch)

        body = _request_body()
        body.pop("instruction", None)
        response = client.post("/api/improve", json=body)
        assert response.status_code == 200

    def test_works_with_a_post_that_has_no_weaknesses(self, client, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "gemini_api_key", "fake-key-for-testing")
        _mock_generation_success(monkeypatch)

        clean_analysis = dict(VALID_ANALYSIS_PAYLOAD, weaknesses=[], suggestions=[])
        response = client.post("/api/improve", json=_request_body(analysis=clean_analysis))
        assert response.status_code == 200


class TestRequestValidation:
    def test_rejects_missing_content(self, client):
        body = _request_body()
        del body["content"]
        response = client.post("/api/improve", json=body)
        assert response.status_code == 400

    def test_rejects_empty_content(self, client):
        response = client.post("/api/improve", json=_request_body(content=""))
        assert response.status_code == 400

    def test_rejects_unsupported_platform(self, client):
        response = client.post("/api/improve", json=_request_body(platform="tiktok"))
        assert response.status_code == 400

    def test_rejects_missing_platform(self, client):
        body = _request_body()
        del body["platform"]
        response = client.post("/api/improve", json=body)
        assert response.status_code == 400

    def test_rejects_missing_analysis(self, client):
        body = _request_body()
        del body["analysis"]
        response = client.post("/api/improve", json=body)
        assert response.status_code == 400

    def test_rejects_malformed_analysis(self, client):
        response = client.post(
            "/api/improve", json=_request_body(analysis={"not": "a real analysis"})
        )
        assert response.status_code == 400

    def test_rejects_an_instruction_over_the_length_cap(self, client):
        response = client.post(
            "/api/improve", json=_request_body(instruction="x" * 501)
        )
        assert response.status_code == 400

    def test_error_envelope_matches_every_other_endpoint(self, client):
        body = client.post("/api/improve", json={}).json()
        assert body["success"] is False
        assert set(body["error"]) <= {"code", "message", "hint"}


class TestAiFailurePaths:
    def test_no_api_key_configured(self, client, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "gemini_api_key", "")

        response = client.post("/api/improve", json=_request_body())
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "AI_UNAVAILABLE"

    def test_network_failure_returns_503_not_500(self, client, monkeypatch):
        from app.config import settings
        from app.utils.errors import ai_unavailable

        monkeypatch.setattr(settings, "gemini_api_key", "fake-key-for-testing")

        async def fail(prompt):
            raise ai_unavailable()

        monkeypatch.setattr(improvement_service, "_call_gemini", fail)

        response = client.post("/api/improve", json=_request_body())
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "AI_UNAVAILABLE"

    def test_invalid_response_returns_502(self, client, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "gemini_api_key", "fake-key-for-testing")

        async def bad(prompt):
            return json.dumps({**VALID_AI_JSON, "hook": ""})

        monkeypatch.setattr(improvement_service, "_call_gemini", bad)

        response = client.post("/api/improve", json=_request_body())
        assert response.status_code == 502
        assert response.json()["error"]["code"] == "AI_RESPONSE_INVALID"


class TestKeyNeverLeaks:
    def test_key_absent_from_success_response(self, client, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "gemini_api_key", "super-secret-key-value")
        _mock_generation_success(monkeypatch)

        response = client.post("/api/improve", json=_request_body())
        assert "super-secret-key-value" not in response.text

    def test_key_absent_from_error_response(self, client, monkeypatch):
        from app.config import settings
        from app.utils.errors import ai_unavailable

        monkeypatch.setattr(settings, "gemini_api_key", "super-secret-key-value")

        async def fail(prompt):
            raise ai_unavailable()

        monkeypatch.setattr(improvement_service, "_call_gemini", fail)

        response = client.post("/api/improve", json=_request_body())
        assert "super-secret-key-value" not in response.text

    def test_key_never_appears_in_the_openapi_schema(self, client, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "gemini_api_key", "super-secret-key-value")
        response = client.get("/openapi.json")
        assert "super-secret-key-value" not in response.text


class TestDoesNotAffectExistingRoutes:
    """The additive schema/router changes must not disturb anything else."""

    def test_upload_route_still_works(self, client, digital_pdf):
        response = client.post(
            "/api/upload", files={"file": ("post.pdf", digital_pdf, "application/pdf")}
        )
        assert response.status_code == 200

    def test_health_route_still_works(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200
        assert "aiAvailable" in response.json()


class TestValidationHintMatchesEndpointShape:
    """Regression test for a real bug found during manual verification: the
    shared validation-error handler used to hardcode a multipart/file hint,
    which was actively wrong for this JSON-body endpoint."""

    def test_bad_platform_hint_does_not_mention_multipart_or_file(self, client):
        response = client.post("/api/improve", json=_request_body(platform="tiktok"))
        hint = response.json()["error"].get("hint", "")
        assert "multipart" not in hint.lower()
        assert "field name 'file'" not in hint

    def test_missing_file_hint_on_upload_still_mentions_file(self, client):
        """The fix must not regress the original, correct behaviour for the
        file-upload endpoints."""
        response = client.post("/api/upload")
        hint = response.json()["error"].get("hint", "")
        assert "file" in hint.lower()
