"""Tests for hallucination detection and confidence scoring."""

import pytest
from unittest.mock import patch, MagicMock

import numpy as np

from app.validation.hallucination import (
    HallucinationDetector,
    ClaimVerification,
    ConfidenceLevel,
    ConfidenceResult,
    _tokenize,
    _split_sentences,
)


@pytest.fixture
def detector():
    return HallucinationDetector(high_threshold=0.7, medium_threshold=0.4)


class TestTokenize:
    def test_basic(self):
        tokens = _tokenize("Hello World! Test 123")
        assert "hello" in tokens
        assert "world" in tokens
        assert "123" in tokens

    def test_empty(self):
        assert _tokenize("") == set()


class TestSplitSentences:
    def test_basic(self):
        text = "First sentence here. Second sentence here. Third one too."
        sentences = _split_sentences(text)
        assert len(sentences) == 3

    def test_short_fragments_filtered(self):
        text = "Ok. This is a real sentence here."
        sentences = _split_sentences(text)
        assert len(sentences) == 1

    def test_abbreviation_safe(self):
        text = "Dr. Smith arrived at 3 p.m. today."
        sentences = _split_sentences(text)
        assert len(sentences) == 1

    def test_conjunction_split(self):
        text = "The hotel has 5 rooms, and a heated pool."
        claims = _split_sentences(text)
        assert len(claims) == 2

    def test_but_conjunction_split(self):
        text = "The rooms are spacious, but the food is terrible."
        claims = _split_sentences(text)
        assert len(claims) == 2

    def test_no_split_on_bare_and(self):
        text = "The Bed and Breakfast is a lovely place to stay."
        claims = _split_sentences(text)
        assert len(claims) == 1

    def test_multi_sentence_with_conjunctions(self):
        text = "Check-in is at 3 PM. The rooms are large, and the pool is heated."
        claims = _split_sentences(text)
        assert len(claims) == 3


class TestContextOverlap:
    def test_identical_text_high_overlap(self, detector):
        text = "The vampire manor has gothic architecture and dark hallways."
        contexts = [text]
        score = detector._compute_context_overlap(text, contexts)
        assert score == 1.0

    def test_unrelated_text_low_overlap(self, detector):
        text = (
            "Quantum physics explains particle behavior at subatomic scales."
        )
        contexts = [
            "The vampire manor has gothic architecture and dark hallways."
        ]
        score = detector._compute_context_overlap(text, contexts)
        assert score < 0.3

    def test_empty_contexts(self, detector):
        score = detector._compute_context_overlap("some text", [])
        assert score == 0.0


class TestSemanticSimilarity:
    def test_similar_text(self, detector):
        text = "The hotel has beautiful dark gothic rooms."
        contexts = ["The resort features gorgeous shadowy gothic chambers."]
        score = detector._compute_semantic_similarity(text, contexts)
        assert score > 0.5

    def test_unrelated_text(self, detector):
        text = "Python programming uses indentation for code blocks."
        contexts = [
            "The vampire manor has gothic architecture and dark hallways."
        ]
        score = detector._compute_semantic_similarity(text, contexts)
        assert score < 0.5

    def test_empty_contexts(self, detector):
        score = detector._compute_semantic_similarity("some text", [])
        assert score == 0.0


class TestSourceAttribution:
    def test_grounded_response(self, detector):
        contexts = [
            "The Vampire Manor features eternal night ambiance "
            "and gothic towers."
        ]
        response = (
            "The Vampire Manor features eternal night ambiance. "
            "It has gothic towers."
        )
        score = detector._compute_source_attribution(response, contexts)
        assert score > 0.5

    def test_ungrounded_response(self, detector):
        contexts = [
            "The Vampire Manor features eternal night ambiance "
            "and gothic towers."
        ]
        response = (
            "Quantum computers leverage superposition for parallel "
            "computation. Neural networks process data through "
            "layered architectures."
        )
        score = detector._compute_source_attribution(response, contexts)
        assert score < 0.3


class TestIntentPreChecks:
    """Tests for refusal and chitchat pre-check logic."""

    def test_refusal_scores_high(self, detector):
        result = detector.score_response(
            "I'm not sure about that, I don't have information on room prices.",
            ["The resort has many rooms available."],
        )
        assert result.level == ConfidenceLevel.HIGH
        assert result.overall_score == 1.0
        assert result.note is not None
        assert "Refusal" in result.note

    def test_refusal_variations(self, detector):
        phrases = [
            "I don't know the answer to that.",
            "I cannot find any relevant details.",
            "I do not have that information.",
            "That is outside my knowledge.",
        ]
        for phrase in phrases:
            result = detector.score_response(phrase, ["some context"])
            assert result.level == ConfidenceLevel.HIGH, (
                f"Failed for: {phrase}"
            )

    def test_refusal_to_dict_includes_note(self, detector):
        result = detector.score_response(
            "I don't have that information.",
            ["context"],
        )
        d = result.to_dict()
        assert "note" in d
        assert "Refusal" in d["note"]

    def test_chitchat_empty_context(self, detector):
        result = detector.score_response("Hello there!", [])
        assert result.level == ConfidenceLevel.MEDIUM
        assert result.note is not None
        assert "Chitchat" in result.note

    def test_chitchat_short_contexts(self, detector):
        result = detector.score_response(
            "Hey, how's it going?",
            ["hi", "hello"],
        )
        assert result.level == ConfidenceLevel.MEDIUM
        assert result.note is not None

    def test_chitchat_not_triggered_for_long_response(self, detector):
        long_response = "word " * 50  # 250 chars, exceeds 200 threshold
        result = detector.score_response(long_response, [])
        # Long response with empty contexts goes through full pipeline (LOW),
        # not the chitchat shortcut
        assert result.level != ConfidenceLevel.MEDIUM or result.note is None

    def test_normal_factual_goes_through_pipeline(self, detector):
        text = (
            "The Vampire Manor has dark gothic hallways "
            "and eternal night ambiance."
        )
        contexts = [text]
        result = detector.score_response(text, contexts)
        assert result.level == ConfidenceLevel.HIGH
        assert result.overall_score >= 0.7
        assert result.note is None  # no pre-check note


class TestScoreResponse:
    def test_high_confidence_identical(self, detector):
        text = (
            "The Vampire Manor has dark gothic hallways "
            "and eternal night ambiance."
        )
        contexts = [text]
        result = detector.score_response(text, contexts)
        assert result.level == ConfidenceLevel.HIGH
        assert result.overall_score >= 0.7

    def test_low_confidence_unrelated(self, detector):
        text = (
            "Quantum computing leverages superposition for parallel "
            "computation across multiple dimensions."
        )
        contexts = [
            "The Vampire Manor features eternal night ambiance "
            "and gothic towers."
        ]
        result = detector.score_response(text, contexts)
        assert result.level == ConfidenceLevel.LOW
        assert result.overall_score < 0.4

    def test_result_to_dict(self, detector):
        text = "The resort has rooms."
        contexts = ["The resort has rooms and amenities."]
        result = detector.score_response(text, contexts)
        d = result.to_dict()
        assert "overall_score" in d
        assert "level" in d
        assert d["level"] in ["HIGH", "MEDIUM", "LOW"]

    def test_result_to_dict_no_note_by_default(self):
        result = ConfidenceResult(
            overall_score=0.8,
            level=ConfidenceLevel.HIGH,
            context_overlap_score=0.7,
            semantic_similarity_score=0.9,
            source_attribution_score=0.8,
        )
        d = result.to_dict()
        assert "note" not in d

    def test_empty_contexts_chitchat_shortcut(self, detector):
        """Short response + empty contexts triggers chitchat pre-check."""
        result = detector.score_response("Some response", [])
        assert result.level == ConfidenceLevel.MEDIUM
        assert result.note is not None


# ──────────────────────────────────────────────────────────────────────
# Claim-level NLI verification (experimental)
# ──────────────────────────────────────────────────────────────────────

def _make_nli_scores(label: str) -> np.ndarray:
    """Build a fake (1, 3) NLI score array for a given dominant label."""
    # Index mapping: 0=contradiction, 1=entailment, 2=neutral
    if label == "SUPPORTED":
        return np.array([[0.05, 0.90, 0.05]])
    elif label == "CONTRADICTED":
        return np.array([[0.85, 0.05, 0.10]])
    else:  # NOT_SUPPORTED / neutral
        return np.array([[0.05, 0.10, 0.85]])


class TestVerifyClaims:
    """Tests for the experimental claim-level NLI verification."""

    def test_supported_claim(self, detector):
        """A claim that IS in the context should be marked SUPPORTED."""
        mock_nli = MagicMock()
        mock_nli.predict.return_value = _make_nli_scores("SUPPORTED")
        detector._nli_model = mock_nli

        result = detector.verify_claims(
            "The Vampire Manor has gothic towers.",
            ["The Vampire Manor features gothic towers and eternal night."],
        )

        assert result.nli_available is True
        assert len(result.claims) == 1
        assert result.claims[0].verdict == "SUPPORTED"
        assert result.grounding_ratio == 1.0
        assert result.num_supported == 1
        assert result.num_unsupported == 0

    def test_unsupported_claim(self, detector):
        """A claim NOT in the context should be marked NOT_SUPPORTED."""
        mock_nli = MagicMock()
        mock_nli.predict.return_value = _make_nli_scores("NOT_SUPPORTED")
        detector._nli_model = mock_nli

        result = detector.verify_claims(
            "Quantum computing uses superposition for parallelism.",
            ["The Vampire Manor features gothic towers and eternal night."],
        )

        assert len(result.claims) == 1
        assert result.claims[0].verdict == "NOT_SUPPORTED"
        assert result.grounding_ratio == 0.0
        assert result.num_unsupported == 1

    def test_contradicted_claim(self, detector):
        """A claim contradicted by context should be marked CONTRADICTED."""
        mock_nli = MagicMock()
        mock_nli.predict.return_value = _make_nli_scores("CONTRADICTED")
        detector._nli_model = mock_nli

        result = detector.verify_claims(
            "The Vampire Manor is brightly lit with sunshine.",
            ["The Vampire Manor features eternal night and dark hallways."],
        )

        assert len(result.claims) == 1
        assert result.claims[0].verdict == "CONTRADICTED"
        assert result.grounding_ratio == 0.0

    def test_mixed_response_grounding_ratio(self, detector):
        """A response with both supported and unsupported claims."""
        mock_nli = MagicMock()

        # First claim: supported.  Second claim: not supported.
        mock_nli.predict.side_effect = [
            _make_nli_scores("SUPPORTED"),
            _make_nli_scores("NOT_SUPPORTED"),
        ]
        detector._nli_model = mock_nli

        response = (
            "The Vampire Manor has gothic towers. "
            "It also has a swimming pool with dolphins."
        )
        contexts = [
            "The Vampire Manor features gothic towers and eternal night."
        ]

        result = detector.verify_claims(response, contexts)

        assert len(result.claims) == 2
        assert result.claims[0].verdict == "SUPPORTED"
        assert result.claims[1].verdict == "NOT_SUPPORTED"
        assert result.grounding_ratio == 0.5
        assert result.num_supported == 1
        assert result.num_unsupported == 1

    def test_nli_model_unavailable(self, detector):
        """When the NLI model can't be loaded, return a graceful fallback."""
        detector._nli_model = None

        with patch.object(
            detector,
            "_get_nli_model",
            return_value=None,
        ):
            result = detector.verify_claims(
                "Some claim here.",
                ["Some context."],
            )

        assert result.nli_available is False
        assert result.note is not None
        assert "unavailable" in result.note.lower()

    def test_empty_contexts_all_unsupported(self, detector):
        """With no contexts, all claims should be NOT_SUPPORTED."""
        mock_nli = MagicMock()
        detector._nli_model = mock_nli

        result = detector.verify_claims(
            "The manor has gothic towers. It features eternal night.",
            [],
        )

        assert len(result.claims) == 2
        assert all(v.verdict == "NOT_SUPPORTED" for v in result.claims)
        assert result.grounding_ratio == 0.0
        # NLI predict should NOT have been called (no contexts)
        mock_nli.predict.assert_not_called()

    def test_no_extractable_claims(self, detector):
        """Very short text with no 3+ word sentences returns empty result."""
        mock_nli = MagicMock()
        detector._nli_model = mock_nli

        result = detector.verify_claims("Ok.", ["Some context here."])

        assert len(result.claims) == 0
        assert result.note is not None


class TestScoreResponseWithClaims:
    """Tests for the combined heuristic + NLI method."""

    def test_returns_both_results(self, detector):
        mock_nli = MagicMock()
        mock_nli.predict.return_value = _make_nli_scores("SUPPORTED")
        detector._nli_model = mock_nli

        text = (
            "The Vampire Manor has dark gothic hallways "
            "and eternal night ambiance."
        )
        contexts = [text]

        confidence, verification = detector.score_response_with_claims(
            text, contexts
        )

        assert isinstance(confidence, ConfidenceResult)
        assert isinstance(verification, ClaimVerification)
        assert confidence.level == ConfidenceLevel.HIGH
        assert verification.nli_available is True
