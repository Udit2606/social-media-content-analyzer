"""AI analysis service: mapping, retry, and failure handling.

No real Gemini API key is required for this file. Every test that exercises
_call_gemini mocks the boundary -- the network call itself -- the same way
test_ocr_service.py mocks Tesseract's output rather than requiring the binary.
What is under test is OUR code: the retry logic, the AI-schema -> public-schema
mapping, and the error translation. A real key exercises the actual Gemini
call and lives in test_ai_end_to_end.py.
"""

import json

import pytest
from google.genai import errors as genai_errors
from pydantic import ValidationError

from app.schemas.ai_analysis import AIAnalysisResult
from app.services import analysis_service, text_metrics
from app.utils.errors import AppError, ErrorCode

VALID_AI_JSON = {
    "overall_score": 68,
    "scores": {
        "hook": 55,
        "clarity": 78,
        "call_to_action": 10,
        "readability": 72,
        "emotional_appeal": 60,
        "audience_relevance": 65,
        "hashtag_quality": 50,
    },
    "tone": {"label": "Confident and informative", "descriptors": ["confident", "technical"]},
    "sentiment": {"label": "positive", "score": 0.4},
    "audience": {
        "primary": "Software engineers",
        "segments": ["backend engineers"],
        "reading_level": "Professional / technical",
    },
    "strengths": [{"title": "Concrete numbers", "detail": "Cites a specific 60% figure."}],
    "weaknesses": [
        {
            "title": "No closing ask",
            "detail": "Ends on a statement with nothing for the reader to do.",
            "severity": "high",
        }
    ],
    "suggestions": [
        {
            "title": "Add a call to action",
            "detail": "Close with a direct question.",
            "severity": "high",
            "example": "What's the hardest migration you've shipped?",
        }
    ],
}

# A real (deterministic) metrics object, used wherever _to_public_schema
# needs one -- computed the same way analyze_text() computes it, so these
# tests exercise the real function rather than a hand-typed stand-in.
SAMPLE_METRICS = text_metrics.compute_metrics(
    "We just shipped our biggest update yet. Latency is down 60%."
)


class TestAvailability:
    def test_unavailable_when_key_is_blank(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "gemini_api_key", "")
        assert analysis_service.is_available() is False

    def test_available_when_key_is_set(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "gemini_api_key", "fake-key-for-testing")
        assert analysis_service.is_available() is True

    @pytest.mark.anyio
    async def test_analyze_text_raises_without_calling_the_network_when_no_key(
        self, monkeypatch
    ):
        """The most important property of the "no key" path: it must fail
        BEFORE attempting a network call, not after a timeout."""
        from app.config import settings

        monkeypatch.setattr(settings, "gemini_api_key", "")

        async def explode(*args, **kwargs):
            raise AssertionError("must not call Gemini when no key is configured")

        monkeypatch.setattr(analysis_service, "_call_gemini", explode)

        with pytest.raises(AppError) as exc:
            await analysis_service.analyze_text("some post text")
        assert exc.value.code == ErrorCode.AI_UNAVAILABLE
        assert exc.value.status_code == 503


class TestMapping:
    """AI-facing schema (snake_case) -> public schema (camelCase), with ids."""

    def test_maps_every_field(self):
        ai_result = AIAnalysisResult.model_validate(VALID_AI_JSON)
        public = analysis_service._to_public_schema(ai_result, SAMPLE_METRICS)

        assert public.overall_score == 68
        assert public.scores.call_to_action == 10
        assert public.tone.label == "Confident and informative"
        assert public.sentiment.score == 0.4
        assert public.strengths[0].detail == "Cites a specific 60% figure."
        assert public.weaknesses[0].severity == "high"
        assert public.suggestions[0].example == "What's the hardest migration you've shipped?"

    def test_assigns_stable_ids(self):
        ai_result = AIAnalysisResult.model_validate(VALID_AI_JSON)
        public = analysis_service._to_public_schema(ai_result, SAMPLE_METRICS)

        assert public.strengths[0].id == "strength-1"
        assert public.weaknesses[0].id == "weakness-1"
        assert public.suggestions[0].id == "suggestion-1"

    def test_empty_lists_map_to_empty_lists(self):
        payload = dict(VALID_AI_JSON, strengths=[], weaknesses=[], suggestions=[])
        ai_result = AIAnalysisResult.model_validate(payload)
        public = analysis_service._to_public_schema(ai_result, SAMPLE_METRICS)

        assert public.strengths == []
        assert public.weaknesses == []
        assert public.suggestions == []

    def test_serialises_to_camel_case(self):
        ai_result = AIAnalysisResult.model_validate(VALID_AI_JSON)
        public = analysis_service._to_public_schema(ai_result, SAMPLE_METRICS)

        dumped = public.model_dump(by_alias=True)
        assert "overallScore" in dumped
        assert "callToAction" in dumped["scores"]
        assert "overall_score" not in dumped

    def test_carries_the_supplied_metrics_through_unchanged(self):
        """metrics is passed in by the caller, not derived from the AI
        result -- this is the seam between the deterministic and AI paths,
        and it must not be silently dropped or recomputed."""
        ai_result = AIAnalysisResult.model_validate(VALID_AI_JSON)
        public = analysis_service._to_public_schema(ai_result, SAMPLE_METRICS)

        assert public.metrics == SAMPLE_METRICS
        assert public.metrics.word_count == SAMPLE_METRICS.word_count


class TestMetricsIntegration:
    """analyze_text() must combine the AI result with metrics computed from
    the ORIGINAL text, independent of AI truncation."""

    @pytest.mark.anyio
    async def test_metrics_reflect_the_full_text_not_the_truncated_prompt(
        self, monkeypatch
    ):
        from app.config import settings

        monkeypatch.setattr(settings, "gemini_api_key", "fake-key-for-testing")
        monkeypatch.setattr(settings, "ai_max_input_chars", 10)

        async def fake_call(prompt):
            # Whatever gets sent to the model is truncated to 10 chars, but
            # the metrics on the RETURNED object must count the whole thing.
            return json.dumps(VALID_AI_JSON)

        monkeypatch.setattr(analysis_service, "_call_gemini", fake_call)

        long_text = "word " * 200
        result = await analysis_service.analyze_text(long_text)

        assert result.metrics.word_count == 200

    @pytest.mark.anyio
    async def test_metrics_are_present_on_every_successful_analysis(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "gemini_api_key", "fake-key-for-testing")

        async def fake_call(prompt):
            return json.dumps(VALID_AI_JSON)

        monkeypatch.setattr(analysis_service, "_call_gemini", fake_call)

        result = await analysis_service.analyze_text("Short post here.")
        assert result.metrics.word_count == 3
        assert result.metrics.readability_score >= 0


class TestTruncation:
    def test_leaves_short_text_untouched(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "ai_max_input_chars", 100)
        assert analysis_service._truncate("short text") == "short text"

    def test_truncates_long_text(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "ai_max_input_chars", 10)
        result = analysis_service._truncate("x" * 500)
        assert len(result) == 10


class TestRetryAndValidation:
    @pytest.mark.anyio
    async def test_succeeds_on_first_valid_response(self, monkeypatch):
        calls = []

        async def fake_call(prompt):
            calls.append(prompt)
            return json.dumps(VALID_AI_JSON)

        monkeypatch.setattr(analysis_service, "_call_gemini", fake_call)

        result = await analysis_service._generate_with_retry("post text")
        assert result.overall_score == 68
        assert len(calls) == 1

    @pytest.mark.anyio
    async def test_retries_once_on_invalid_response_then_succeeds(self, monkeypatch):
        responses = iter([
            json.dumps({**VALID_AI_JSON, "overall_score": 500}),  # out of range
            json.dumps(VALID_AI_JSON),                            # corrected
        ])
        calls = []

        async def fake_call(prompt):
            calls.append(prompt)
            return next(responses)

        monkeypatch.setattr(analysis_service, "_call_gemini", fake_call)

        result = await analysis_service._generate_with_retry("post text")
        assert result.overall_score == 68
        assert len(calls) == 2
        # The retry prompt must reference the failure, or it will not correct.
        assert "schema" in calls[1].lower() or "error" in calls[1].lower()

    @pytest.mark.anyio
    async def test_gives_up_after_two_invalid_responses(self, monkeypatch):
        async def fake_call(prompt):
            return json.dumps({**VALID_AI_JSON, "overall_score": 999})

        monkeypatch.setattr(analysis_service, "_call_gemini", fake_call)

        with pytest.raises(AppError) as exc:
            await analysis_service._generate_with_retry("post text")
        assert exc.value.code == ErrorCode.AI_RESPONSE_INVALID
        assert exc.value.status_code == 502

    @pytest.mark.anyio
    async def test_malformed_json_is_treated_as_invalid_not_a_crash(self, monkeypatch):
        async def fake_call(prompt):
            return "this is not json at all {["

        monkeypatch.setattr(analysis_service, "_call_gemini", fake_call)

        with pytest.raises(AppError) as exc:
            await analysis_service._generate_with_retry("post text")
        assert exc.value.code == ErrorCode.AI_RESPONSE_INVALID


class TestFullPipeline:
    @pytest.mark.anyio
    async def test_analyze_text_end_to_end_with_mocked_network(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "gemini_api_key", "fake-key-for-testing")

        async def fake_call(prompt):
            return json.dumps(VALID_AI_JSON)

        monkeypatch.setattr(analysis_service, "_call_gemini", fake_call)

        result = await analysis_service.analyze_text("We just shipped our biggest update yet.")
        assert result.overall_score == 68
        assert result.strengths[0].id == "strength-1"

    @pytest.mark.anyio
    async def test_long_text_is_truncated_before_reaching_the_network(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "gemini_api_key", "fake-key-for-testing")
        monkeypatch.setattr(settings, "ai_max_input_chars", 50)

        received = {}

        async def fake_call(prompt):
            received["prompt"] = prompt
            return json.dumps(VALID_AI_JSON)

        monkeypatch.setattr(analysis_service, "_call_gemini", fake_call)

        await analysis_service.analyze_text("x" * 10_000)
        assert len(received["prompt"]) <= 50


class TestErrorTranslation:
    """The exact exception -> AppError mapping inside _call_gemini, with a
    real (but unreachable) client so the SDK's own error paths are exercised
    rather than assumed."""

    @pytest.mark.anyio
    async def test_client_error_becomes_ai_unavailable(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "gemini_api_key", "fake-key-for-testing")
        analysis_service._client_initialised = False
        analysis_service._client = None

        class FakeModels:
            async def generate_content(self, **kwargs):
                raise genai_errors.ClientError(
                    code=401, response_json={"error": {"message": "invalid key"}}
                )

        class FakeAio:
            models = FakeModels()

        class FakeClient:
            aio = FakeAio()

        monkeypatch.setattr(analysis_service, "_get_client", lambda: FakeClient())

        with pytest.raises(AppError) as exc:
            await analysis_service._call_gemini("prompt")
        assert exc.value.code == ErrorCode.AI_UNAVAILABLE
        assert exc.value.status_code == 503
        # The real cause must never reach the client.
        assert "invalid key" not in exc.value.message

    @pytest.mark.anyio
    async def test_empty_response_becomes_ai_response_invalid(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "gemini_api_key", "fake-key-for-testing")

        class EmptyResponse:
            @property
            def text(self):
                return None

        class FakeModels:
            async def generate_content(self, **kwargs):
                return EmptyResponse()

        class FakeAio:
            models = FakeModels()

        class FakeClient:
            aio = FakeAio()

        monkeypatch.setattr(analysis_service, "_get_client", lambda: FakeClient())

        with pytest.raises(AppError) as exc:
            await analysis_service._call_gemini("prompt")
        assert exc.value.code == ErrorCode.AI_RESPONSE_INVALID


@pytest.fixture
def anyio_backend():
    return "asyncio"
