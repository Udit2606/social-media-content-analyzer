"""Deterministic text metrics: word count, character count, sentence count,
average sentence length, reading time, and readability.

Every value here is computed with plain string operations and a well-known
formula -- no network call, no AI model, no external dependency. This is a
deliberate split from analysis_service.py: sentiment and tone genuinely need
semantic interpretation of what the text MEANS, which only an LLM can do, but
"how many words are there" and "how easy is this to read" are just counting
and arithmetic. Running those through an LLM would make them slower, costlier,
and non-reproducible for zero benefit -- the same input must always produce
the same word count, and only a deterministic function guarantees that.

Readability specifically uses the Flesch Reading Ease formula (Flesch, 1948),
the same formula behind the readability score in Microsoft Word and most
writing tools. It needs a syllable count per word, which has no reliable
dictionary-free algorithm; the heuristic here (count vowel-sound groups, drop
a trailing silent "e") is the standard approximation used by widely-adopted
tools such as the `textstat` and `syllables` packages, and is accurate enough
for a directional score -- it is not claimed to be linguistically exact.
"""

import re
from typing import List

from app.schemas.analysis import ContentMetrics

# Splits on one or more sentence-ending marks, consuming the whitespace after
# them so "Hi! Bye." -> ["Hi", "Bye"] rather than ["Hi", " Bye", ""].
_SENTENCE_BOUNDARY_RE = re.compile(r"[.!?]+(?:\s+|$)")

# One or more consecutive vowels count as a single syllable "beat", which is
# the standard heuristic: "beautiful" -> "eau" + "i" + "u" = 3 groups.
_VOWEL_GROUP_RE = re.compile(r"[aeiouy]+")

# A conservative, widely-cited adult silent-reading speed. Slower estimates
# (~200 wpm) are preferred over faster ones (~250-300 wpm) so the reported
# time is a safe upper bound rather than an optimistic one.
_READING_WORDS_PER_MINUTE = 200


def compute_metrics(text: str) -> ContentMetrics:
    """Compute every deterministic metric for one piece of text.

    Safe to call with empty or whitespace-only text -- every field degrades to
    a sane zero value rather than raising or dividing by zero.
    """
    stripped = text.strip()
    words = stripped.split()

    word_count = len(words)
    character_count = len(stripped)
    sentence_count = _count_sentences(stripped)
    avg_words_per_sentence = (
        round(word_count / sentence_count, 1) if sentence_count else 0.0
    )
    reading_time_seconds = _estimate_reading_time_seconds(word_count)

    readability_score = _flesch_reading_ease(words, sentence_count)
    readability_level = _readability_level(readability_score)

    return ContentMetrics(
        character_count=character_count,
        word_count=word_count,
        sentence_count=sentence_count,
        avg_words_per_sentence=avg_words_per_sentence,
        reading_time_seconds=reading_time_seconds,
        readability_score=readability_score,
        readability_level=readability_level,
    )


# -- Internals ----------------------------------------------------------


def _count_sentences(text: str) -> int:
    """Count sentences by splitting on `. ! ?`.

    No attempt is made to special-case abbreviations ("Dr.", "e.g.") or
    decimal numbers ("3.5") -- that needs real sentence-boundary detection,
    which is disproportionate for a directional metric. Any non-empty text
    counts as at least one sentence, so a caption with no punctuation at all
    ("just a phrase") is not reported as containing zero sentences.
    """
    if not text:
        return 0
    fragments = [part for part in _SENTENCE_BOUNDARY_RE.split(text) if part.strip()]
    return max(1, len(fragments))


def _estimate_reading_time_seconds(word_count: int) -> int:
    if word_count == 0:
        return 0
    seconds = (word_count / _READING_WORDS_PER_MINUTE) * 60
    return max(1, round(seconds))


def _count_syllables(word: str) -> int:
    """Heuristic syllable count: vowel-sound groups, minus a trailing silent e.

    A token with no letters at all -- "60%", "123", an emoji -- still counts
    as 1: it occupies one slot in the word count that `_flesch_reading_ease`
    divides by, so treating it as 0 syllables would understate the syllable
    density of any post containing numbers, which social posts often do
    ("60% faster"). The only token that should genuinely score 0 is the
    empty string itself, which real input never produces (words come from
    `str.split()`, which never yields empty tokens) but which callers of
    this function directly may still pass.
    """
    if not word:
        return 0

    letters = re.sub(r"[^a-z]", "", word.lower())
    if not letters:
        return 1

    groups = _VOWEL_GROUP_RE.findall(letters)
    count = len(groups)

    # "like" -> 1 syllable, not 2: the trailing "e" is silent, not its own
    # vowel group. Only drop it when doing so leaves at least one syllable,
    # so "the" (1 group) stays at 1 rather than becoming 0.
    if letters.endswith("e") and count > 1:
        count -= 1

    return max(1, count)


def _flesch_reading_ease(words: List[str], sentence_count: int) -> float:
    """206.835 - 1.015*(words/sentences) - 84.6*(syllables/words), clamped to 0-100.

    Higher is easier to read. The raw formula can run slightly outside 0-100
    for unusual text (e.g. one very long sentence of short words can exceed
    100); it is clamped here because every score in this app's UI is
    displayed on a 0-100 scale and an out-of-range number would look broken
    rather than merely unusual.
    """
    word_count = len(words)
    if word_count == 0 or sentence_count == 0:
        return 0.0

    syllable_count = sum(_count_syllables(word) for word in words)

    score = (
        206.835
        - 1.015 * (word_count / sentence_count)
        - 84.6 * (syllable_count / word_count)
    )
    return round(max(0.0, min(100.0, score)), 1)


def _readability_level(score: float) -> str:
    """Bucket a Flesch score into a short, human label.

    Thresholds follow the standard Flesch interpretation table, collapsed
    from its usual seven bands into five so the label stays a quick read
    rather than requiring the user to know what "grade 9" means.
    """
    if score >= 80:
        return "Very easy to read"
    if score >= 60:
        return "Easy to read"
    if score >= 50:
        return "Fairly difficult"
    if score >= 30:
        return "Difficult"
    return "Very difficult"
