"""Real Gemini calls, no mocking.

Skipped unless GEMINI_API_KEY is actually set in the environment running the
tests -- this repository ships with no key, so these do not run by default and
have not been exercised against the live API in this session. They exist so
that whoever adds a key (locally or in CI) gets one command that proves the
real integration works, the same way test_ocr_end_to_end.py does for Tesseract.

To run these for real:
    export GEMINI_API_KEY=your-key-from-aistudio.google.com
    pytest tests/test_ai_end_to_end.py -v
"""

import pytest

from app.config import settings
from app.services import analysis_service, improvement_service, platform_service

requires_gemini_key = pytest.mark.skipif(
    not settings.gemini_api_key.strip(),
    reason="GEMINI_API_KEY is not set in this environment",
)


@pytest.fixture(autouse=True)
def _fresh_gemini_client_per_test():
    """Force each test to build its own Gemini client, bound to ITS OWN event loop.

    Each of the three AI services caches a module-level client singleton,
    created once and reused for the lifetime of the process -- correct and
    required in production, where uvicorn keeps one event loop alive for the
    server's entire lifetime. pytest-anyio does the opposite: by default every
    async test function gets a brand new event loop. Without this fixture, a
    client built during test A survives (as a plain module attribute) into
    test B, still bound to test A's now-closed loop, and every network call
    in test B fails with "RuntimeError: Event loop is closed" -- a test
    ordering artifact, not anything a real user could ever hit.
    """
    for module in (analysis_service, improvement_service, platform_service):
        module._client = None
        module._client_initialised = False
    yield

STRONG_POST = (
    "We cut our API latency by 60% this quarter -- with zero downtime during the "
    "migration.\n\nThe hardest part wasn't the code, it was moving live traffic "
    "without anyone noticing.\n\nWhat's the trickiest migration you've shipped? "
    "I'd love to hear it.\n\n#engineering #backend"
)

WEAK_POST = "we did a thing today it was fine i guess"


@requires_gemini_key
class TestRealAnalysis:
    @pytest.mark.anyio
    async def test_analyzes_a_real_post(self):
        result = await analysis_service.analyze_text(STRONG_POST)

        assert 0 <= result.overall_score <= 100
        assert 0 <= result.scores.hook <= 100
        assert 0 <= result.scores.call_to_action <= 100
        assert result.sentiment.label in ("positive", "neutral", "negative", "mixed")
        assert -1 <= result.sentiment.score <= 1
        assert isinstance(result.tone.label, str) and result.tone.label

        # Deterministic metrics ride along with every real analysis too --
        # not mocked here, so this is the actual text_metrics output.
        assert result.metrics.word_count == len(STRONG_POST.split())
        assert 0 <= result.metrics.readability_score <= 100

    @pytest.mark.anyio
    async def test_strong_post_scores_higher_than_weak_post(self):
        """A real calibration check, not just a schema check: the model should
        meaningfully distinguish a strong post from a low-effort one."""
        strong = await analysis_service.analyze_text(STRONG_POST)
        weak = await analysis_service.analyze_text(WEAK_POST)

        assert strong.overall_score > weak.overall_score

    @pytest.mark.anyio
    async def test_post_with_a_clear_cta_scores_higher_on_cta(self):
        with_cta = await analysis_service.analyze_text(
            "Check out our new feature. Try it today and tell us what you think!"
        )
        without_cta = await analysis_service.analyze_text(
            "We released a new feature yesterday."
        )
        assert with_cta.scores.call_to_action >= without_cta.scores.call_to_action

    @pytest.mark.anyio
    async def test_short_text_is_still_analyzed_not_rejected(self):
        """The prompt explicitly asks the model not to refuse short input."""
        result = await analysis_service.analyze_text("Ship it.")
        assert 0 <= result.overall_score <= 100


@requires_gemini_key
class TestRealApiRoundTrip:
    def test_full_pipeline_over_http(self, client, digital_pdf):
        response = client.post(
            "/api/analyze", files={"file": ("post.pdf", digital_pdf, "application/pdf")}
        )
        assert response.status_code == 200

        body = response.json()
        assert body["success"] is True
        assert 0 <= body["analysis"]["overallScore"] <= 100
        assert len(body["analysis"]["suggestions"]) >= 0

    def test_health_reports_the_real_model(self, client):
        body = client.get("/api/health").json()
        assert body["aiAvailable"] is True
        assert body["aiModel"] == settings.gemini_model


@requires_gemini_key
class TestRealImprovement:
    """Real calls to the "Improve My Post" pipeline: analyse, then improve."""

    @pytest.mark.anyio
    async def test_improves_a_real_post_for_linkedin(self):
        analysis = await analysis_service.analyze_text(WEAK_POST)

        improved = await improvement_service.generate_improved_post(
            content=WEAK_POST, platform="linkedin", analysis=analysis
        )

        assert improved.hook.strip()
        assert improved.body.strip()
        assert improved.cta.strip()
        assert improved.full_post.strip()
        assert isinstance(improved.hashtags, list)

    @pytest.mark.anyio
    async def test_same_post_reads_differently_across_platforms(self):
        """The real calibration check for this feature: LinkedIn and X
        versions of the same post must not be interchangeable."""
        analysis = await analysis_service.analyze_text(STRONG_POST)

        linkedin = await improvement_service.generate_improved_post(
            content=STRONG_POST, platform="linkedin", analysis=analysis
        )
        x_version = await improvement_service.generate_improved_post(
            content=STRONG_POST, platform="x", analysis=analysis
        )

        assert linkedin.full_post != x_version.full_post
        # X's guidance asks for terseness; this is a soft expectation, not a
        # hard contract, but a wildly longer X post would indicate the
        # platform guidance was not followed at all.
        assert len(x_version.full_post) <= len(linkedin.full_post) + 100

    @pytest.mark.anyio
    async def test_does_not_introduce_a_number_absent_from_the_original(self):
        """A best-effort check for the anti-hallucination rule. Not proof --
        no automated check can fully verify "no invented facts" -- but a
        clearly new, specific number appearing in the output that is not in
        the source text would be a concrete, checkable red flag."""
        source = "We shipped a small fix today. It seems to be working well."
        analysis = await analysis_service.analyze_text(source)

        improved = await improvement_service.generate_improved_post(
            content=source, platform="linkedin", analysis=analysis
        )

        import re

        source_numbers = set(re.findall(r"\d+", source))
        output_numbers = set(re.findall(r"\d+", improved.full_post))
        invented = output_numbers - source_numbers
        assert not invented, f"numbers present in output but not in source: {invented}"

    @pytest.mark.anyio
    async def test_follows_a_user_instruction(self):
        analysis = await analysis_service.analyze_text(STRONG_POST)

        improved = await improvement_service.generate_improved_post(
            content=STRONG_POST,
            platform="linkedin",
            analysis=analysis,
            instruction="Keep it under 100 characters total.",
        )
        # Soft check: the instruction should meaningfully shorten the post,
        # even if the model does not hit the exact character count.
        assert len(improved.full_post) < len(STRONG_POST)

    def test_full_pipeline_over_http(self, client, digital_pdf):
        analyze_response = client.post(
            "/api/analyze", files={"file": ("post.pdf", digital_pdf, "application/pdf")}
        )
        assert analyze_response.status_code == 200
        analyzed = analyze_response.json()

        improve_response = client.post(
            "/api/improve",
            json={
                "content": analyzed["extraction"]["text"],
                "platform": "linkedin",
                "analysis": analyzed["analysis"],
            },
        )
        assert improve_response.status_code == 200

        improved = improve_response.json()["improved"]
        assert improved["hook"].strip()
        assert improved["fullPost"].strip()


@requires_gemini_key
class TestRealPlatformOptimization:
    """Real Gemini calls for POST /api/platform-analysis.

    Added alongside analysis and improvement rather than left as
    mock-only coverage: this is the one AI service that had never been
    exercised against the live API before a real key existed to test it with.
    """

    @pytest.mark.anyio
    async def test_scores_a_real_post_for_a_real_platform(self):
        result = await platform_service.analyze_for_platform(STRONG_POST, "linkedin")

        assert 0 <= result.engagement_score <= 100
        assert result.recommended_tone.strip()
        assert result.recommended_length.strip()
        assert result.hook_recommendation.strip()
        assert result.cta_recommendation.strip()
        assert isinstance(result.hashtag_recommendation, list)

    @pytest.mark.anyio
    async def test_same_post_scores_differently_across_platforms(self):
        """The real calibration check: LinkedIn and X are different enough
        audiences that a professional post should not fit both equally."""
        linkedin = await platform_service.analyze_for_platform(STRONG_POST, "linkedin")
        x_platform = await platform_service.analyze_for_platform(STRONG_POST, "x")

        assert linkedin.recommended_tone != x_platform.recommended_tone

    @pytest.mark.anyio
    async def test_every_supported_platform_returns_a_valid_result(self):
        for platform in ("linkedin", "instagram", "x", "facebook"):
            result = await platform_service.analyze_for_platform(STRONG_POST, platform)
            assert 0 <= result.engagement_score <= 100


@pytest.fixture
def anyio_backend():
    return "asyncio"
