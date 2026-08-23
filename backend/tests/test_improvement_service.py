"""Improve My Post service: prompt building, mapping, retry, and failure
handling.

No real Gemini key is required. _call_gemini is mocked at the boundary, same
discipline as test_analysis_service.py -- what's under test is our own
prompt-building, retry logic, and error translation, not Gemini's output.
"""

import json

import pytest
from google.genai import errors as genai_errors

from app.schemas.ai_improvement import AIImprovedPost
from app.schemas.analysis import ContentAnalysis
from app.services import improvement_service
from app.utils.errors import AppError, ErrorCode

VALID_ANALYSIS = ContentAnalysis.model_validate({
    "overall_score": 68,
    "scores": {
        "hook": 55, "clarity": 78, "call_to_action": 10,
        "readability": 72, "emotional_appeal": 60,
        "audience_relevance": 65, "hashtag_quality": 50,
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
        "character_count": 62,
        "word_count": 12,
        "sentence_count": 2,
        "avg_words_per_sentence": 6.0,
        "reading_time_seconds": 4,
        "readability_score": 70.0,
        "readability_level": "Easy to read",
    },
})

EMPTY_ANALYSIS = ContentAnalysis.model_validate({
    **VALID_ANALYSIS.model_dump(by_alias=True),
    "weaknesses": [],
    "suggestions": [],
})

VALID_AI_JSON = {
    "hook": "We cut latency by 60% -- with zero downtime.",
    "body": "Six months of work went into rebuilding the ingestion layer from scratch.",
    "cta": "What's the trickiest migration you've shipped?",
    "hashtags": ["engineering", "backend"],
    "full_post": "We cut latency by 60% -- with zero downtime.\n\nSix months of work went into rebuilding the ingestion layer from scratch.\n\nWhat's the trickiest migration you've shipped?\n\n#engineering #backend",
}

ORIGINAL_TEXT = "We just shipped our biggest update yet. Latency is down 60%."


class TestAvailability:
    def test_unavailable_when_key_is_blank(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "gemini_api_key", "")
        assert improvement_service.is_available() is False

    @pytest.mark.anyio
    async def test_generate_raises_without_network_call_when_no_key(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "gemini_api_key", "")

        async def explode(prompt):
            raise AssertionError("must not call Gemini when no key is configured")

        monkeypatch.setattr(improvement_service, "_call_gemini", explode)

        with pytest.raises(AppError) as exc:
            await improvement_service.generate_improved_post(
                content=ORIGINAL_TEXT, platform="linkedin", analysis=VALID_ANALYSIS
            )
        assert exc.value.code == ErrorCode.AI_UNAVAILABLE
        assert exc.value.status_code == 503


class TestPromptBuilding:
    """The prompt is the actual product here -- it is what makes the four
    platforms differ and what grounds the model in known problems."""

    def test_includes_the_original_content(self):
        prompt = improvement_service._build_prompt(
            ORIGINAL_TEXT, "linkedin", VALID_ANALYSIS, None
        )
        assert ORIGINAL_TEXT in prompt

    def test_includes_platform_specific_guidance(self):
        linkedin = improvement_service._build_prompt(ORIGINAL_TEXT, "linkedin", VALID_ANALYSIS, None)
        instagram = improvement_service._build_prompt(ORIGINAL_TEXT, "instagram", VALID_ANALYSIS, None)

        assert "LinkedIn" in linkedin
        assert "Instagram" in instagram
        # The two platforms must not receive identical guidance -- that is the
        # entire mechanism behind "do not make every post sound identical".
        assert linkedin != instagram

    @pytest.mark.parametrize("platform", ["linkedin", "instagram", "x", "facebook"])
    def test_every_supported_platform_has_guidance(self, platform):
        prompt = improvement_service._build_prompt(ORIGINAL_TEXT, platform, VALID_ANALYSIS, None)
        assert improvement_service._PLATFORM_GUIDANCE[platform] in prompt

    def test_includes_known_weaknesses_and_suggestions(self):
        prompt = improvement_service._build_prompt(ORIGINAL_TEXT, "linkedin", VALID_ANALYSIS, None)
        assert "No closing ask" in prompt
        assert "Add a CTA" in prompt

    def test_handles_a_post_with_no_weaknesses_or_suggestions(self):
        """A genuinely strong post is a legitimate input, not an error case."""
        prompt = improvement_service._build_prompt(ORIGINAL_TEXT, "linkedin", EMPTY_ANALYSIS, None)
        assert "already working" in prompt.lower() or "no weaknesses" in prompt.lower()

    def test_includes_user_instruction_when_given(self):
        prompt = improvement_service._build_prompt(
            ORIGINAL_TEXT, "linkedin", VALID_ANALYSIS, "make it punchier"
        )
        assert "make it punchier" in prompt

    def test_omits_instruction_section_when_not_given(self):
        prompt = improvement_service._build_prompt(ORIGINAL_TEXT, "linkedin", VALID_ANALYSIS, None)
        assert "USER INSTRUCTION" not in prompt

    def test_blank_instruction_is_treated_as_absent(self):
        prompt = improvement_service._build_prompt(ORIGINAL_TEXT, "linkedin", VALID_ANALYSIS, "   ")
        assert "USER INSTRUCTION" not in prompt

    def test_truncates_long_content(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "ai_max_input_chars", 20)
        prompt = improvement_service._build_prompt("x" * 500, "linkedin", VALID_ANALYSIS, None)
        assert "x" * 500 not in prompt
        assert "x" * 20 in prompt


class TestMapping:
    def test_maps_every_field(self):
        ai_result = AIImprovedPost.model_validate(VALID_AI_JSON)
        public = improvement_service._to_public_schema(ai_result)

        assert public.hook == VALID_AI_JSON["hook"]
        assert public.body == VALID_AI_JSON["body"]
        assert public.cta == VALID_AI_JSON["cta"]
        assert public.hashtags == ["engineering", "backend"]
        assert public.full_post == VALID_AI_JSON["full_post"]

    def test_serialises_to_camel_case(self):
        ai_result = AIImprovedPost.model_validate(VALID_AI_JSON)
        public = improvement_service._to_public_schema(ai_result)
        dumped = public.model_dump(by_alias=True)

        assert "fullPost" in dumped
        assert "full_post" not in dumped

    def test_empty_hashtags_list_is_preserved(self):
        payload = dict(VALID_AI_JSON, hashtags=[])
        ai_result = AIImprovedPost.model_validate(payload)
        public = improvement_service._to_public_schema(ai_result)
        assert public.hashtags == []


class TestRetryAndValidation:
    @pytest.mark.anyio
    async def test_succeeds_on_first_valid_response(self, monkeypatch):
        calls = []

        async def fake_call(prompt):
            calls.append(prompt)
            return json.dumps(VALID_AI_JSON)

        monkeypatch.setattr(improvement_service, "_call_gemini", fake_call)

        result = await improvement_service._generate_with_retry("prompt")
        assert result.hook == VALID_AI_JSON["hook"]
        assert len(calls) == 1

    @pytest.mark.anyio
    async def test_retries_once_on_invalid_response_then_succeeds(self, monkeypatch):
        responses = iter([
            json.dumps({**VALID_AI_JSON, "hook": ""}),  # violates min_length=1
            json.dumps(VALID_AI_JSON),
        ])
        calls = []

        async def fake_call(prompt):
            calls.append(prompt)
            return next(responses)

        monkeypatch.setattr(improvement_service, "_call_gemini", fake_call)

        result = await improvement_service._generate_with_retry("prompt")
        assert result.hook == VALID_AI_JSON["hook"]
        assert len(calls) == 2
        assert "schema" in calls[1].lower() or "error" in calls[1].lower()

    @pytest.mark.anyio
    async def test_gives_up_after_two_invalid_responses(self, monkeypatch):
        async def fake_call(prompt):
            return json.dumps({**VALID_AI_JSON, "hook": ""})

        monkeypatch.setattr(improvement_service, "_call_gemini", fake_call)

        with pytest.raises(AppError) as exc:
            await improvement_service._generate_with_retry("prompt")
        assert exc.value.code == ErrorCode.AI_RESPONSE_INVALID
        assert exc.value.status_code == 502

    @pytest.mark.anyio
    async def test_malformed_json_is_treated_as_invalid_not_a_crash(self, monkeypatch):
        async def fake_call(prompt):
            return "not json {["

        monkeypatch.setattr(improvement_service, "_call_gemini", fake_call)

        with pytest.raises(AppError) as exc:
            await improvement_service._generate_with_retry("prompt")
        assert exc.value.code == ErrorCode.AI_RESPONSE_INVALID


class TestFullPipeline:
    @pytest.mark.anyio
    async def test_generate_improved_post_end_to_end_with_mocked_network(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "gemini_api_key", "fake-key-for-testing")

        async def fake_call(prompt):
            return json.dumps(VALID_AI_JSON)

        monkeypatch.setattr(improvement_service, "_call_gemini", fake_call)

        result = await improvement_service.generate_improved_post(
            content=ORIGINAL_TEXT,
            platform="linkedin",
            analysis=VALID_ANALYSIS,
            instruction="make it punchier",
        )
        assert result.hook == VALID_AI_JSON["hook"]
        assert result.hashtags == ["engineering", "backend"]


class TestErrorTranslation:
    @pytest.mark.anyio
    async def test_client_error_becomes_ai_unavailable(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "gemini_api_key", "fake-key-for-testing")
        improvement_service._client_initialised = False
        improvement_service._client = None

        class FakeModels:
            async def generate_content(self, **kwargs):
                raise genai_errors.ClientError(
                    code=401, response_json={"error": {"message": "invalid key"}}
                )

        class FakeAio:
            models = FakeModels()

        class FakeClient:
            aio = FakeAio()

        monkeypatch.setattr(improvement_service, "_get_client", lambda: FakeClient())

        with pytest.raises(AppError) as exc:
            await improvement_service._call_gemini("prompt")
        assert exc.value.code == ErrorCode.AI_UNAVAILABLE
        assert exc.value.status_code == 503
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

        monkeypatch.setattr(improvement_service, "_get_client", lambda: FakeClient())

        with pytest.raises(AppError) as exc:
            await improvement_service._call_gemini("prompt")
        assert exc.value.code == ErrorCode.AI_RESPONSE_INVALID


@pytest.fixture
def anyio_backend():
    return "asyncio"
