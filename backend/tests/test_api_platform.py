"""POST /api/platform-analysis over real HTTP.

The AI network boundary is mocked, so no Gemini key is required.
"""

import json

import pytest

from app.services import platform_service

VALID_AI_JSON = {
    "engagement_score": 72,
    "recommended_tone": "Professional and insight-led",
    "recommended_length": "900-1300 characters, 3-4 short paragraphs",
    "hook_recommendation": "Lead with the 60% figure so it survives the fold.",
    "cta_recommendation": "Close with a direct question to invite comments.",
    "hashtag_recommendation": ["engineering", "backend"],
}


def _mock_success(monkeypatch):
    async def fake(prompt):
        return json.dumps(VALID_AI_JSON)

    monkeypatch.setattr(platform_service, "_call_gemini", fake)


def _body(**overrides):
    body = {"text": "We shipped a thing. Latency is down 60%.", "platform": "linkedin"}
    body.update(overrides)
    return body


class TestSuccessPath:
    def test_returns_the_optimization(self, client, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "gemini_api_key", "fake-key-for-testing")
        _mock_success(monkeypatch)

        response = client.post("/api/platform-analysis", json=_body())
        assert response.status_code == 200

        body = response.json()
        assert body["success"] is True
        assert body["platform"] == "linkedin"
        assert body["optimization"]["engagementScore"] == 72

    def test_response_shape_matches_documented_contract(self, client, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "gemini_api_key", "fake-key-for-testing")
        _mock_success(monkeypatch)

        body = client.post("/api/platform-analysis", json=_body()).json()

        assert set(body) == {"success", "platform", "optimization"}
        # Exactly the seven display fields the UI renders.
        assert set(body["optimization"]) == {
            "engagementScore",
            "recommendedTone",
            "recommendedLength",
            "hookRecommendation",
            "ctaRecommendation",
            "hashtagRecommendation",
        }

    @pytest.mark.parametrize("platform", ["linkedin", "instagram", "x", "facebook"])
    def test_accepts_every_supported_platform(self, client, monkeypatch, platform):
        from app.config import settings

        monkeypatch.setattr(settings, "gemini_api_key", "fake-key-for-testing")
        _mock_success(monkeypatch)

        response = client.post("/api/platform-analysis", json=_body(platform=platform))
        assert response.status_code == 200
        assert response.json()["platform"] == platform

    def test_platform_reaches_the_prompt(self, client, monkeypatch):
        """Proof the selected platform actually changes what is sent to the AI,
        rather than being echoed back cosmetically."""
        from app.config import settings

        monkeypatch.setattr(settings, "gemini_api_key", "fake-key-for-testing")
        received = {}

        async def fake(prompt):
            received["prompt"] = prompt
            return json.dumps(VALID_AI_JSON)

        monkeypatch.setattr(platform_service, "_call_gemini", fake)

        client.post("/api/platform-analysis", json=_body(platform="instagram"))
        assert "instagram" in received["prompt"].lower()
        assert platform_service._PLATFORM_GUIDANCE["instagram"] in received["prompt"]


class TestRequestValidation:
    def test_rejects_missing_text(self, client):
        assert client.post("/api/platform-analysis", json={"platform": "linkedin"}).status_code == 400

    def test_rejects_empty_text(self, client):
        assert client.post("/api/platform-analysis", json=_body(text="")).status_code == 400

    def test_rejects_missing_platform(self, client):
        assert client.post("/api/platform-analysis", json={"text": "hi"}).status_code == 400

    def test_rejects_unsupported_platform(self, client):
        assert client.post("/api/platform-analysis", json=_body(platform="tiktok")).status_code == 400

    def test_error_envelope_matches_every_other_endpoint(self, client):
        body = client.post("/api/platform-analysis", json={}).json()
        assert body["success"] is False
        assert set(body["error"]) <= {"code", "message", "hint"}


class TestAiFailurePaths:
    def test_no_api_key_returns_503(self, client, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "gemini_api_key", "")

        response = client.post("/api/platform-analysis", json=_body())
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "AI_UNAVAILABLE"

    def test_invalid_ai_response_returns_502(self, client, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "gemini_api_key", "fake-key-for-testing")

        async def bad(prompt):
            return json.dumps({**VALID_AI_JSON, "engagement_score": 999})

        monkeypatch.setattr(platform_service, "_call_gemini", bad)

        response = client.post("/api/platform-analysis", json=_body())
        assert response.status_code == 502
        assert response.json()["error"]["code"] == "AI_RESPONSE_INVALID"

    def test_key_never_leaks(self, client, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "gemini_api_key", "super-secret-key-value")
        _mock_success(monkeypatch)

        response = client.post("/api/platform-analysis", json=_body())
        assert "super-secret-key-value" not in response.text


class TestExistingRoutesUnaffected:
    """The whole point of a separate endpoint: nothing else changes."""

    def test_analyze_text_still_works(self, client, monkeypatch):
        from app.schemas.ai_analysis import AIAnalysisResult
        from app.services import analysis_service, text_metrics
        from tests.test_api_analyze import VALID_AI_JSON as ANALYSIS_JSON

        async def fake(text):
            return analysis_service._to_public_schema(
                AIAnalysisResult.model_validate(ANALYSIS_JSON),
                text_metrics.compute_metrics(text),
            )

        monkeypatch.setattr(analysis_service, "analyze_text", fake)

        response = client.post("/api/analyze-text", json={"text": "some post"})
        assert response.status_code == 200
        # Still platform-agnostic: no optimization field leaked in.
        assert "optimization" not in response.json()

    def test_upload_still_works(self, client, digital_pdf):
        response = client.post(
            "/api/upload", files={"file": ("post.pdf", digital_pdf, "application/pdf")}
        )
        assert response.status_code == 200

    def test_health_still_works(self, client):
        assert client.get("/api/health").status_code == 200
