"""Platform-specific optimization service.

No Gemini key required: _call_gemini is mocked at the network boundary, the
same discipline as the other AI service tests. What is under test is our own
prompt building, mapping, retry logic and error translation.
"""

import json

import pytest
from google.genai import errors as genai_errors

from app.schemas.ai_platform_optimization import AIPlatformOptimization
from app.services import platform_service
from app.utils.errors import AppError, ErrorCode

VALID_AI_JSON = {
    "engagement_score": 72,
    "recommended_tone": "Professional and insight-led",
    "recommended_length": "900-1300 characters, 3-4 short paragraphs",
    "hook_recommendation": "Lead with the 60% figure so it survives the fold.",
    "cta_recommendation": "Close with a direct question to invite comments.",
    "hashtag_recommendation": ["engineering", "backend"],
}

POST_TEXT = "We just shipped our biggest update yet. Latency is down 60%."


class TestAvailability:
    def test_unavailable_when_key_is_blank(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "gemini_api_key", "")
        assert platform_service.is_available() is False

    @pytest.mark.anyio
    async def test_raises_without_network_call_when_no_key(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "gemini_api_key", "")

        async def explode(prompt):
            raise AssertionError("must not call Gemini when no key is configured")

        monkeypatch.setattr(platform_service, "_call_gemini", explode)

        with pytest.raises(AppError) as exc:
            await platform_service.analyze_for_platform(POST_TEXT, "linkedin")
        assert exc.value.code == ErrorCode.AI_UNAVAILABLE
        assert exc.value.status_code == 503


class TestPromptBuilding:
    """The prompt is what makes the four platforms produce different answers."""

    def test_includes_the_post_text(self):
        prompt = platform_service._build_prompt(POST_TEXT, "linkedin")
        assert POST_TEXT in prompt

    def test_includes_the_named_platform(self):
        prompt = platform_service._build_prompt(POST_TEXT, "instagram")
        assert "instagram" in prompt.lower()

    @pytest.mark.parametrize("platform", ["linkedin", "instagram", "x", "facebook"])
    def test_every_supported_platform_has_guidance(self, platform):
        prompt = platform_service._build_prompt(POST_TEXT, platform)
        assert platform_service._PLATFORM_GUIDANCE[platform] in prompt

    def test_platforms_receive_different_prompts(self):
        """If two platforms got the same prompt, per-platform advice would be
        impossible -- this is the mechanism the whole feature rests on."""
        prompts = {
            p: platform_service._build_prompt(POST_TEXT, p)
            for p in ["linkedin", "instagram", "x", "facebook"]
        }
        assert len(set(prompts.values())) == 4

    def test_truncates_long_text(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "ai_max_input_chars", 20)
        prompt = platform_service._build_prompt("x" * 500, "linkedin")
        assert "x" * 500 not in prompt
        assert "x" * 20 in prompt


class TestMapping:
    def test_maps_every_field(self):
        ai_result = AIPlatformOptimization.model_validate(VALID_AI_JSON)
        public = platform_service._to_public_schema(ai_result)

        assert public.engagement_score == 72
        assert public.recommended_tone == VALID_AI_JSON["recommended_tone"]
        assert public.recommended_length == VALID_AI_JSON["recommended_length"]
        assert public.hook_recommendation == VALID_AI_JSON["hook_recommendation"]
        assert public.cta_recommendation == VALID_AI_JSON["cta_recommendation"]
        assert public.hashtag_recommendation == ["engineering", "backend"]

    def test_serialises_to_camel_case(self):
        ai_result = AIPlatformOptimization.model_validate(VALID_AI_JSON)
        dumped = platform_service._to_public_schema(ai_result).model_dump(by_alias=True)

        assert "engagementScore" in dumped
        assert "hashtagRecommendation" in dumped
        assert "engagement_score" not in dumped

    def test_empty_hashtag_list_is_preserved(self):
        payload = dict(VALID_AI_JSON, hashtag_recommendation=[])
        ai_result = AIPlatformOptimization.model_validate(payload)
        assert platform_service._to_public_schema(ai_result).hashtag_recommendation == []


class TestRetryAndValidation:
    @pytest.mark.anyio
    async def test_succeeds_on_first_valid_response(self, monkeypatch):
        calls = []

        async def fake_call(prompt):
            calls.append(prompt)
            return json.dumps(VALID_AI_JSON)

        monkeypatch.setattr(platform_service, "_call_gemini", fake_call)

        result = await platform_service._generate_with_retry("prompt")
        assert result.engagement_score == 72
        assert len(calls) == 1

    @pytest.mark.anyio
    async def test_retries_once_then_succeeds(self, monkeypatch):
        responses = iter([
            json.dumps({**VALID_AI_JSON, "engagement_score": 500}),  # out of range
            json.dumps(VALID_AI_JSON),
        ])
        calls = []

        async def fake_call(prompt):
            calls.append(prompt)
            return next(responses)

        monkeypatch.setattr(platform_service, "_call_gemini", fake_call)

        result = await platform_service._generate_with_retry("prompt")
        assert result.engagement_score == 72
        assert len(calls) == 2
        assert "schema" in calls[1].lower() or "error" in calls[1].lower()

    @pytest.mark.anyio
    async def test_gives_up_after_two_invalid_responses(self, monkeypatch):
        async def fake_call(prompt):
            return json.dumps({**VALID_AI_JSON, "engagement_score": 999})

        monkeypatch.setattr(platform_service, "_call_gemini", fake_call)

        with pytest.raises(AppError) as exc:
            await platform_service._generate_with_retry("prompt")
        assert exc.value.code == ErrorCode.AI_RESPONSE_INVALID
        assert exc.value.status_code == 502

    @pytest.mark.anyio
    async def test_malformed_json_is_not_a_crash(self, monkeypatch):
        async def fake_call(prompt):
            return "not json {["

        monkeypatch.setattr(platform_service, "_call_gemini", fake_call)

        with pytest.raises(AppError) as exc:
            await platform_service._generate_with_retry("prompt")
        assert exc.value.code == ErrorCode.AI_RESPONSE_INVALID


class TestErrorTranslation:
    @pytest.mark.anyio
    async def test_client_error_becomes_ai_unavailable(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "gemini_api_key", "fake-key-for-testing")

        class FakeModels:
            async def generate_content(self, **kwargs):
                raise genai_errors.ClientError(
                    code=401, response_json={"error": {"message": "invalid key"}}
                )

        class FakeAio:
            models = FakeModels()

        class FakeClient:
            aio = FakeAio()

        monkeypatch.setattr(platform_service, "_get_client", lambda: FakeClient())

        with pytest.raises(AppError) as exc:
            await platform_service._call_gemini("prompt")
        assert exc.value.code == ErrorCode.AI_UNAVAILABLE
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

        monkeypatch.setattr(platform_service, "_get_client", lambda: FakeClient())

        with pytest.raises(AppError) as exc:
            await platform_service._call_gemini("prompt")
        assert exc.value.code == ErrorCode.AI_RESPONSE_INVALID


class TestExistingPipelineUntouched:
    """This feature must not alter the general analysis pipeline."""

    @staticmethod
    def _imported_names(module) -> set:
        """Actual import statements, via AST.

        Deliberately not a substring search over the source: the modules
        reference each other by name in explanatory comments, and a text match
        would fail on prose rather than on a real dependency.
        """
        import ast
        import inspect

        tree = ast.parse(inspect.getsource(module))
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    names.add(node.module)
                names.update(alias.name for alias in node.names)
        return names

    def test_platform_service_does_not_import_analysis_service(self):
        assert "analysis_service" not in self._imported_names(platform_service)

    def test_analysis_service_does_not_import_platform_service(self):
        from app.services import analysis_service

        assert "platform_service" not in self._imported_names(analysis_service)

    def test_platform_optimization_is_not_part_of_content_analysis(self):
        """The general analysis contract must be unchanged by this feature."""
        from app.schemas.analysis import ContentAnalysis

        assert set(ContentAnalysis.model_fields) == {
            "overall_score",
            "scores",
            "tone",
            "sentiment",
            "audience",
            "strengths",
            "weaknesses",
            "suggestions",
            "metrics",
        }


@pytest.fixture
def anyio_backend():
    return "asyncio"
