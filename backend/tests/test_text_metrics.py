"""Deterministic text metrics: word/character/sentence counts, reading time,
and Flesch Reading Ease readability.

Every test here is a pure function call with a hand-checked expected value --
no mocking, no fixtures beyond plain strings, because nothing in this module
touches the network, the AI, or anything non-reproducible.
"""

import pytest

from app.services import text_metrics


class TestWordAndCharacterCount:
    def test_counts_words_by_whitespace(self):
        metrics = text_metrics.compute_metrics("one two three four five")
        assert metrics.word_count == 5

    def test_character_count_matches_stripped_length(self):
        metrics = text_metrics.compute_metrics("  hello world  ")
        assert metrics.character_count == len("hello world")

    def test_empty_text_yields_all_zeros(self):
        metrics = text_metrics.compute_metrics("")
        assert metrics.word_count == 0
        assert metrics.character_count == 0
        assert metrics.sentence_count == 0
        assert metrics.avg_words_per_sentence == 0.0
        assert metrics.reading_time_seconds == 0

    def test_whitespace_only_text_yields_all_zeros(self):
        """A single space passes the API's min_length=1, so this must not
        raise a division-by-zero once it reaches the metrics function."""
        metrics = text_metrics.compute_metrics("   ")
        assert metrics.word_count == 0
        assert metrics.sentence_count == 0


class TestSentenceCount:
    def test_counts_terminal_punctuation(self):
        metrics = text_metrics.compute_metrics("First sentence. Second sentence! Third?")
        assert metrics.sentence_count == 3

    def test_text_with_no_punctuation_is_still_one_sentence(self):
        metrics = text_metrics.compute_metrics("just a caption with no period")
        assert metrics.sentence_count == 1

    def test_trailing_punctuation_does_not_add_a_phantom_sentence(self):
        metrics = text_metrics.compute_metrics("One sentence.")
        assert metrics.sentence_count == 1

    def test_multiple_punctuation_marks_do_not_over_count(self):
        """An ellipsis or "?!" must not be read as several sentence breaks."""
        metrics = text_metrics.compute_metrics("Wait... really?! Yes.")
        assert metrics.sentence_count == 3


class TestAverageWordsPerSentence:
    def test_divides_words_by_sentences(self):
        metrics = text_metrics.compute_metrics("One two three. Four five six.")
        assert metrics.avg_words_per_sentence == 3.0

    def test_rounds_to_one_decimal_place(self):
        metrics = text_metrics.compute_metrics("One two three four five. Six seven.")
        assert metrics.avg_words_per_sentence == pytest.approx(3.5)


class TestReadingTime:
    def test_short_text_rounds_up_to_at_least_one_second(self):
        metrics = text_metrics.compute_metrics("One word.")
        assert metrics.reading_time_seconds >= 1

    def test_scales_with_word_count(self):
        short = text_metrics.compute_metrics("word " * 50)
        long = text_metrics.compute_metrics("word " * 500)
        assert long.reading_time_seconds > short.reading_time_seconds

    def test_roughly_matches_two_hundred_words_per_minute(self):
        """400 words at the documented 200 wpm assumption should be ~120s."""
        metrics = text_metrics.compute_metrics("word " * 400)
        assert 110 <= metrics.reading_time_seconds <= 130


class TestReadability:
    def test_simple_short_sentences_score_high(self):
        """Short words, short sentences: Flesch rewards this heavily."""
        metrics = text_metrics.compute_metrics(
            "The cat sat. The dog ran. We won."
        )
        assert metrics.readability_score >= 80
        assert metrics.readability_level == "Very easy to read"

    def test_long_dense_sentences_score_low(self):
        """Long, multisyllabic, single-sentence text: Flesch penalises this."""
        text = (
            "The comprehensive organizational restructuring initiative "
            "necessitates unprecedented interdepartmental collaboration "
            "among stakeholders responsible for implementing multifaceted "
            "operational transformations across geographically distributed "
            "administrative jurisdictions worldwide."
        )
        metrics = text_metrics.compute_metrics(text)
        assert metrics.readability_score < 30
        assert metrics.readability_level == "Very difficult"

    def test_score_is_always_within_zero_to_one_hundred(self):
        """The raw formula can mathematically exceed this range; the
        function must clamp it so the UI's 0-100 scale is never violated."""
        very_simple = text_metrics.compute_metrics("I am. I am. I am. I am.")
        assert 0.0 <= very_simple.readability_score <= 100.0

    def test_readability_level_matches_documented_thresholds(self):
        assert text_metrics._readability_level(95) == "Very easy to read"
        assert text_metrics._readability_level(80) == "Very easy to read"
        assert text_metrics._readability_level(79.9) == "Easy to read"
        assert text_metrics._readability_level(60) == "Easy to read"
        assert text_metrics._readability_level(59.9) == "Fairly difficult"
        assert text_metrics._readability_level(50) == "Fairly difficult"
        assert text_metrics._readability_level(49.9) == "Difficult"
        assert text_metrics._readability_level(30) == "Difficult"
        assert text_metrics._readability_level(29.9) == "Very difficult"
        assert text_metrics._readability_level(0) == "Very difficult"

    def test_empty_text_does_not_raise(self):
        metrics = text_metrics.compute_metrics("")
        assert metrics.readability_score == 0.0


class TestSyllableCounting:
    """The one genuinely heuristic part of this module. Checked against
    known, unambiguous cases rather than every English word."""

    @pytest.mark.parametrize(
        "word,expected",
        [
            ("cat", 1),
            ("the", 1),
            ("like", 1),      # silent trailing e must not count as a syllable
            ("hello", 2),
            ("beautiful", 3),
            ("a", 1),
            ("", 0),
            # No letters at all: still 1, not 0 -- see the docstring on
            # _count_syllables for why treating these as 0 would understate
            # syllable density for any post containing a number.
            ("60%", 1),
            ("123", 1),
        ],
    )
    def test_known_words(self, word, expected):
        assert text_metrics._count_syllables(word) == expected

    def test_never_returns_a_negative_count(self):
        assert text_metrics._count_syllables("e") >= 1


class TestDeterminism:
    """The property that justifies not using an LLM for any of this."""

    def test_identical_input_always_produces_identical_output(self):
        text = "We just shipped our biggest update yet. Latency is down 60%."
        first = text_metrics.compute_metrics(text)
        second = text_metrics.compute_metrics(text)
        assert first == second

    def test_no_network_or_ai_dependency_is_imported(self):
        """A structural guard against this module quietly growing an AI call
        in a future edit -- it exists specifically to avoid that."""
        import ast
        import inspect

        tree = ast.parse(inspect.getsource(text_metrics))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)

        forbidden = {"google", "google.genai", "httpx", "app.services.analysis_service"}
        assert not (imported & forbidden)
