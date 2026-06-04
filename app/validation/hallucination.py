"""Hallucination detection via confidence scoring against RAG contexts."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from prometheus_client import Counter, Histogram

from ..monitoring.logging_utils import logger

RESPONSE_CONFIDENCE = Histogram(
    "mrc_response_confidence",
    "Confidence score of LLM responses",
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)
HALLUCINATIONS_DETECTED = Counter(
    "mrc_hallucinations_detected",
    "Responses flagged as low confidence",
    ["level"],
)


class ConfidenceLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


_REFUSAL_PHRASES = [
    "i don't have",
    "i do not have",
    "i'm not sure",
    "i am not sure",
    "i cannot find",
    "i can't find",
    "no information available",
    "i don't know",
    "i do not know",
    "outside my knowledge",
]


@dataclass
class ConfidenceResult:
    overall_score: float
    level: ConfidenceLevel
    context_overlap_score: float
    semantic_similarity_score: float
    source_attribution_score: float
    note: str | None = None

    def to_dict(self) -> Dict:
        d = {
            "overall_score": round(self.overall_score, 4),
            "level": self.level.value,
            "context_overlap_score": round(self.context_overlap_score, 4),
            "semantic_similarity_score": round(self.semantic_similarity_score, 4),
            "source_attribution_score": round(self.source_attribution_score, 4),
        }
        if self.note is not None:
            d["note"] = self.note
        return d


# --- Claim-level NLI verification (experimental) ---
# NLI labels returned by cross-encoder/nli-deberta-v3-small:
#   0 = contradiction, 1 = entailment, 2 = neutral
_NLI_LABEL_MAP = {0: "CONTRADICTED", 1: "SUPPORTED", 2: "NOT_SUPPORTED"}


@dataclass
class ClaimVerdict:
    """Verdict for a single claim checked against context via NLI."""

    claim: str
    verdict: str  # "SUPPORTED", "NOT_SUPPORTED", or "CONTRADICTED"
    best_context: str
    confidence: float

    def to_dict(self) -> dict:
        return {
            "claim": self.claim,
            "verdict": self.verdict,
            "best_context": self.best_context,
            "confidence": round(self.confidence, 4),
        }


@dataclass
class ClaimVerification:
    """Result of running claim-level NLI verification on a full response."""

    claims: List[ClaimVerdict] = field(default_factory=list)
    grounding_ratio: float = 0.0  # fraction of SUPPORTED claims
    num_supported: int = 0
    num_unsupported: int = 0
    nli_available: bool = True
    note: Optional[str] = None

    def to_dict(self) -> dict:
        d = {
            "grounding_ratio": round(self.grounding_ratio, 4),
            "num_supported": self.num_supported,
            "num_unsupported": self.num_unsupported,
            "nli_available": self.nli_available,
            "claims": [c.to_dict() for c in self.claims],
        }
        if self.note is not None:
            d["note"] = self.note
        return d


def _tokenize(text: str) -> set[str]:
    """Return lowercased word tokens as a set."""
    return set(re.findall(r"\w+", text.lower()))


_ABBREV_SAFE = r"(?<!Mr)(?<!Ms)(?<!Dr)(?<!Jr)(?<!Sr)(?<!vs)(?<!etc)(?<!Prof)(?<!Inc)(?<!Ltd)(?<!St)"
_CLAUSE_CONJ = re.compile(r",\s*\b(and|but|yet|while|although|however)\b\s+", re.IGNORECASE)


def _split_sentences(text: str) -> List[str]:
    """Split text into atomic claims: sentence boundaries + clause conjunctions."""
    # Step 1: split on sentence-ending punctuation, safe around abbreviations
    raw = re.split(rf"{_ABBREV_SAFE}(?<=[.!?])\s+", text.strip())
    # Step 2: sub-split on ", and/but/yet..." where comma signals a clause boundary
    claims: List[str] = []
    for sentence in raw:
        parts = _CLAUSE_CONJ.split(sentence)
        # re.split with groups returns [chunk, conj, chunk, ...] — take every other
        claims.extend(parts[::2])
    return [c.strip().rstrip(",") for c in claims if len(c.split()) >= 3]


def _is_refusal(text: str) -> bool:
    """Check if the response is an honest refusal (cheap string matching)."""
    lower = text.lower()
    return any(phrase in lower for phrase in _REFUSAL_PHRASES)


def _is_chitchat(response_text: str, contexts: List[str]) -> bool:
    """Check if this is ungrounded chitchat (no meaningful context, short reply)."""
    if len(response_text) >= 200:
        return False
    if not contexts:
        return True
    return all(len(ctx.strip()) < 20 for ctx in contexts)


class HallucinationDetector:
    def __init__(
        self,
        high_threshold: float = 0.7,
        medium_threshold: float = 0.4,
        overlap_weight: float = 0.2,
        semantic_weight: float = 0.2,
        attribution_weight: float = 0.6,
    ):
        self.high_threshold = high_threshold
        self.medium_threshold = medium_threshold
        self.overlap_weight = overlap_weight
        self.semantic_weight = semantic_weight
        self.attribution_weight = attribution_weight
        self._model = None
        self._nli_model = None

    def _get_model(self):
        """Lazy-load the sentence transformer model."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer("all-MiniLM-L6-v2")
            except ImportError:
                logger.warning(
                    "sentence-transformers not available for hallucination detection"
                )
        return self._model

    def _get_nli_model(self):
        """Lazy-load the NLI cross-encoder model (experimental)."""
        if self._nli_model is None:
            try:
                from sentence_transformers import CrossEncoder

                self._nli_model = CrossEncoder(
                    "cross-encoder/nli-deberta-v3-small"
                )
            except (ImportError, RuntimeError, OSError) as exc:
                logger.warning(f"NLI cross-encoder not available: {exc}")
        return self._nli_model

    # ------------------------------------------------------------------
    # Claim-level NLI verification (experimental)
    # ------------------------------------------------------------------

    def verify_claims(
        self,
        response_text: str,
        contexts: List[str],
    ) -> ClaimVerification:
        """Run claim-level NLI verification against context chunks.

        This is an *experimental* addition that catches "right vocabulary,
        wrong facts" hallucinations by checking whether each claim in the
        response is actually entailed by the retrieved context.

        The method is intentionally kept separate from ``score_response``
        because NLI inference adds latency.  Call it explicitly when you
        want the deeper check, or use ``score_response_with_claims`` for
        the combined result.
        """
        t0 = time.perf_counter()
        nli = self._get_nli_model()

        if nli is None:
            logger.info("nli_verification_skipped", extra={"reason": "model_unavailable"})
            return ClaimVerification(
                nli_available=False,
                note="NLI model unavailable — skipping claim verification",
            )

        claims = _split_sentences(response_text)

        if not claims:
            logger.info("nli_verification_skipped", extra={"reason": "no_claims"})
            return ClaimVerification(note="No claims extracted from response")

        if not contexts:
            latency_ms = round((time.perf_counter() - t0) * 1000, 1)
            verdicts = [
                ClaimVerdict(
                    claim=c,
                    verdict="NOT_SUPPORTED",
                    best_context="",
                    confidence=1.0,
                )
                for c in claims
            ]
            logger.info("nli_verification_complete", extra={
                "num_claims": len(claims),
                "supported": 0,
                "not_supported": len(claims),
                "contradicted": 0,
                "grounding_ratio": 0.0,
                "latency_ms": latency_ms,
                "reason": "no_contexts",
            })
            return ClaimVerification(
                claims=verdicts,
                grounding_ratio=0.0,
                num_supported=0,
                num_unsupported=len(claims),
            )

        try:
            import numpy as np

            verdicts: List[ClaimVerdict] = []

            for claim in claims:
                # Build premise-hypothesis pairs for every context chunk
                pairs = [[ctx, claim] for ctx in contexts]
                scores = nli.predict(pairs)  # shape (n_contexts, 3)

                # Ensure scores is 2-D even for a single context
                scores = np.atleast_2d(scores)

                # Find the best entailment and contradiction scores
                # across all context chunks.
                best_ent_score = -1.0
                best_ent_ctx = 0
                best_contra_score = -1.0
                best_contra_ctx = 0
                best_neutral_score = -1.0
                best_neutral_ctx = 0

                for ctx_i, score_row in enumerate(scores):
                    ent_val = float(score_row[1])
                    contra_val = float(score_row[0])
                    neutral_val = float(score_row[2])
                    if ent_val > best_ent_score:
                        best_ent_score = ent_val
                        best_ent_ctx = ctx_i
                    if contra_val > best_contra_score:
                        best_contra_score = contra_val
                        best_contra_ctx = ctx_i
                    if neutral_val > best_neutral_score:
                        best_neutral_score = neutral_val
                        best_neutral_ctx = ctx_i

                # Decision: entailment wins if it's the strongest signal
                # from any context chunk.
                if (
                    best_ent_score >= best_contra_score
                    and best_ent_score >= best_neutral_score
                ):
                    verdict = "SUPPORTED"
                    best_ctx = contexts[best_ent_ctx]
                    confidence = best_ent_score
                elif best_contra_score >= best_neutral_score:
                    verdict = "CONTRADICTED"
                    best_ctx = contexts[best_contra_ctx]
                    confidence = best_contra_score
                else:
                    verdict = "NOT_SUPPORTED"
                    best_ctx = contexts[best_neutral_ctx]
                    confidence = best_neutral_score

                verdicts.append(
                    ClaimVerdict(
                        claim=claim,
                        verdict=verdict,
                        best_context=best_ctx,
                        confidence=round(confidence, 4),
                    )
                )

            num_supported = sum(
                1 for v in verdicts if v.verdict == "SUPPORTED"
            )
            num_unsupported = sum(
                1 for v in verdicts if v.verdict != "SUPPORTED"
            )
            grounding = num_supported / len(verdicts) if verdicts else 0.0

            latency_ms = round((time.perf_counter() - t0) * 1000, 1)
            num_contradicted = sum(1 for v in verdicts if v.verdict == "CONTRADICTED")

            logger.info("nli_verification_complete", extra={
                "num_claims": len(claims),
                "supported": num_supported,
                "not_supported": num_unsupported - num_contradicted,
                "contradicted": num_contradicted,
                "grounding_ratio": round(grounding, 4),
                "latency_ms": latency_ms,
            })

            for v in verdicts:
                logger.debug("claim_verdict", extra={
                    "claim": v.claim[:120],
                    "verdict": v.verdict,
                    "confidence": v.confidence,
                })

            return ClaimVerification(
                claims=verdicts,
                grounding_ratio=round(grounding, 4),
                num_supported=num_supported,
                num_unsupported=num_unsupported,
            )

        except Exception as exc:
            latency_ms = round((time.perf_counter() - t0) * 1000, 1)
            logger.warning("nli_verification_failed", extra={
                "error": str(exc),
                "latency_ms": latency_ms,
            })
            return ClaimVerification(
                nli_available=False,
                note=f"Claim verification error: {exc}",
            )

    def score_response_with_claims(
        self,
        response_text: str,
        rag_contexts: List[str],
    ) -> Tuple[ConfidenceResult, ClaimVerification]:
        """Run both the fast heuristic score AND NLI claim verification.

        Returns a tuple of ``(ConfidenceResult, ClaimVerification)``.
        Use this when you want the full picture -- the heuristic score
        gives a quick signal, while the NLI verification catches subtle
        factual errors that token-overlap and embedding similarity miss.
        """
        confidence = self.score_response(response_text, rag_contexts)
        verification = self.verify_claims(response_text, rag_contexts)
        return confidence, verification

    def _compute_context_overlap(
        self, response_text: str, contexts: List[str]
    ) -> float:
        """Compute token-level overlap ratio between response and contexts."""
        if not contexts:
            return 0.0

        response_tokens = _tokenize(response_text)
        if not response_tokens:
            return 0.0

        context_tokens = set()
        for ctx in contexts:
            context_tokens.update(_tokenize(ctx))

        overlap = response_tokens & context_tokens
        return len(overlap) / len(response_tokens)

    def _compute_semantic_similarity(
        self, response_text: str, contexts: List[str]
    ) -> float:
        """Return max cosine similarity between response and context embeddings."""
        model = self._get_model()
        if model is None or not contexts:
            return 0.0

        try:
            import numpy as np

            resp_emb = model.encode([response_text])[0]
            ctx_emb = model.encode(contexts)

            similarities = []
            for emb in ctx_emb:
                cos_sim = float(
                    np.dot(resp_emb, emb)
                    / (np.linalg.norm(resp_emb) * np.linalg.norm(emb) + 1e-10)
                )
                similarities.append(cos_sim)

            return max(similarities) if similarities else 0.0
        except Exception as e:
            logger.warning(f"Semantic similarity computation failed: {e}")
            return 0.0

    def _compute_source_attribution(
        self, response_text: str, contexts: List[str]
    ) -> float:
        """Return the fraction of response sentences grounded in context."""
        if not contexts:
            return 0.0

        sentences = _split_sentences(response_text)
        if not sentences:
            return 0.0

        context_tokens = set()
        for ctx in contexts:
            context_tokens.update(_tokenize(ctx))

        grounded = 0
        for sentence in sentences:
            sent_tokens = _tokenize(sentence)
            if not sent_tokens:
                continue
            overlap_ratio = len(sent_tokens & context_tokens) / len(sent_tokens)
            if overlap_ratio >= 0.3:
                grounded += 1

        return grounded / len(sentences)

    def score_response(
        self,
        response_text: str,
        rag_contexts: List[str],
    ) -> ConfidenceResult:
        """Score a response for hallucination risk.

        Pre-checks (cheap, no ML):
        1. Refusal detection -- honest "I don't know" answers score HIGH.
        2. Chitchat detection -- short replies with no real context score MEDIUM.
        """
        # --- Pre-check: refusal ------------------------------------------------
        if _is_refusal(response_text):
            logger.info("Intent pre-check: refusal detected, skipping scoring")
            return ConfidenceResult(
                overall_score=1.0,
                level=ConfidenceLevel.HIGH,
                context_overlap_score=0.0,
                semantic_similarity_score=0.0,
                source_attribution_score=0.0,
                note="Refusal detected; honest admission of uncertainty is safe.",
            )

        # --- Pre-check: chitchat -----------------------------------------------
        if _is_chitchat(response_text, rag_contexts):
            logger.info("Intent pre-check: chitchat detected, skipping scoring")
            return ConfidenceResult(
                overall_score=0.5,
                level=ConfidenceLevel.MEDIUM,
                context_overlap_score=0.0,
                semantic_similarity_score=0.0,
                source_attribution_score=0.0,
                note="Chitchat or greeting; grounding is not applicable.",
            )

        # --- Full scoring pipeline ---------------------------------------------
        overlap = self._compute_context_overlap(response_text, rag_contexts)
        semantic = self._compute_semantic_similarity(response_text, rag_contexts)
        attribution = self._compute_source_attribution(response_text, rag_contexts)

        overall = (
            self.overlap_weight * overlap
            + self.semantic_weight * semantic
            + self.attribution_weight * attribution
        )

        if overall >= self.high_threshold:
            level = ConfidenceLevel.HIGH
        elif overall >= self.medium_threshold:
            level = ConfidenceLevel.MEDIUM
        else:
            level = ConfidenceLevel.LOW

        RESPONSE_CONFIDENCE.observe(overall)
        HALLUCINATIONS_DETECTED.labels(level=level.value).inc()

        logger.info(
            f"Confidence score: {overall:.3f} ({level.value}) "  # noqa: E231
            f"[overlap={overlap:.3f}, semantic={semantic:.3f}, "  # noqa: E231
            f"attribution={attribution:.3f}]"  # noqa: E231
        )

        return ConfidenceResult(
            overall_score=overall,
            level=level,
            context_overlap_score=overlap,
            semantic_similarity_score=semantic,
            source_attribution_score=attribution,
        )
