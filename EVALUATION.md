# Evaluation & Ablation Studies

Quantitative evaluation of the Monster Game Resort Concierge across retrieval quality, conversation memory, hallucination detection, and cost.

---

## Retrieval Quality (Ground Truth Evaluation)

13 queries evaluated against a ground truth answer key (`evals/retrieval_ground_truth.json`). Each query is sent through the retrieval pipeline and checked: did the retrieved chunks contain the expected snippets?

**Live mode (real AdvancedRAG pipeline — BM25 + dense + cross-encoder reranker):**

| Metric | Score |
|--------|-------|
| MRR | 0.756 |
| Recall@3 | 76.9% |
| Recall@10 | 78.5% |
| Precision@3 | 46.2% |

11 of 13 queries find the correct answer in position 1 or 2. Two queries fail completely (Werewolf spa, Frankenstein dining) — both are amenity lookups where the chunker splits the relevant section across chunk boundaries. Fix path: parent-document retrieval or overlapping chunk windows.

```bash
# Run against live RAG pipeline
python evals/eval_retrieval.py --live

# Run against mock corpus (fast, reproducible, no ML deps)
python evals/eval_retrieval.py

# Compare against previous run
python evals/eval_retrieval.py --compare-last
```

---

## Retrieval Ablation

How much does each retrieval stage contribute? Isolating BM25, dense vectors, fusion, and reranking.

| Config | MRR@5 | Precision@5 | Latency (ms) |
|--------|-------|-------------|---------------|
| BM25-only | 0.42 | 0.15 | 0.1 |
| Dense-only (ChromaDB) | 0.75 | 0.30 | 9.0 |
| Hybrid (BM25 + Dense + RRF) | 0.58 | 0.30 | 10.2 |
| Hybrid + Cross-Encoder Reranker | 0.67 | 0.33 | 1,087 |

> Run `python scripts/ablation_retrieval.py` to reproduce.

**Key finding:** Dense-only achieves the best MRR (0.75) on this small corpus. The cross-encoder reranker adds ~1s latency for marginal precision gain (+0.03). On a larger, noisier corpus the reranker's benefit would be more pronounced.

---

## Conversation Memory

Results from context management experiments (`scripts/test_context_management.py`).

### Token Scaling

Prompt tokens scale approximately **12.5x** from turn 0 to turn 20. At turn 0 the prompt is ~95 tokens; by turn 20 it is ~1,190 tokens. This is the primary driver of per-conversation cost growth.

### Window Size vs. Information Retention

| Window Strategy | Retains Dietary Restrictions (msg 1)? | Retains Room Preference (msg 3)? | Retains Name (msg 0)? |
|-----------------|---------------------------------------|----------------------------------|-----------------------|
| Last 2 messages | No | Yes | No |
| Last 5 messages | Depends on turn | Yes | Depends on turn |
| Full history (10 messages) | Yes | Yes | Yes |

**Key finding:** A sliding window of 2 loses dietary restrictions mentioned early in the conversation. This is a real failure mode for a concierge that takes food orders. The auto-summarization approach (below) is the mitigation.

### Auto-Summarization

- **Trigger:** Fires at 12 messages in a conversation.
- **Mechanism:** LLM-based summarization of the oldest messages into a rolling summary. Falls back to regex extraction if the LLM call fails.
- **Trade-off:** Summarization compresses detail. A guest who mentioned a shellfish allergy in message 2 may lose that detail if the summary is lossy. The threshold of 12 balances token cost against information loss.

---

## Hallucination Detection

Two-tier system: fast heuristic scoring on every response, plus optional NLI claim verification for deeper factual checking.

### Tier 1: Heuristic Scoring

**Intent Pre-Checks (no ML, runs first):**

| Check | Condition | Result |
|-------|-----------|--------|
| Refusal detection | Response contains "I don't know", "I cannot find", etc. | HIGH (1.0) — honest uncertainty is safe |
| Chitchat detection | Short response (< 200 chars) + empty/trivial contexts | MEDIUM (0.5) — grounding not applicable |

If neither pre-check fires, the response goes through the full scoring pipeline.

**Signal Weights:**

| Signal | Weight | Method |
|--------|--------|--------|
| Source attribution | 60% | Sentence-level grounding: fraction of response claims with >= 30% token overlap against any context chunk |
| Token overlap | 20% | Token-level intersection ratio (response tokens vs. context tokens) |
| Semantic similarity | 20% | Max cosine similarity between response and context embeddings (`all-MiniLM-L6-v2`) |

Attribution is weighted highest because it measures whether each claim traces back to a source, not just whether the response "sounds like" the context.

**Confidence Thresholds:**

| Level | Threshold | Interpretation |
|-------|-----------|----------------|
| HIGH | >= 0.7 | Response is well-grounded in retrieved context |
| MEDIUM | >= 0.4 | Partially grounded; some claims may not be in the knowledge base |
| LOW | < 0.4 | Significant portions of the response are not supported by retrieved context |

### Tier 2: NLI Claim Verification (Experimental)

Claim-level entailment checking via `cross-encoder/nli-deberta-v3-small`. This layer catches the failure mode where a response uses the right vocabulary but states wrong facts.

1. Response is split into atomic claims (abbreviation-safe sentence splitting + clause conjunction splitting on ", and/but/yet...")
2. Each claim is checked against every context chunk via NLI (entailment / contradiction / neutral)
3. Best entailment score across all contexts determines the verdict per claim

**Output:** `ClaimVerification` with per-claim verdicts (SUPPORTED / NOT_SUPPORTED / CONTRADICTED), grounding ratio, and latency.

Called explicitly via `verify_claims()` or combined with Tier 1 via `score_response_with_claims()`. Adds ~50-200ms latency depending on claim count.

### Experiment Results (Before vs. After Upgrade)

| Experiment | Old Score | Old Level | New Score | New Level | Fix |
|------------|-----------|-----------|-----------|-----------|-----|
| Faithful Paraphrase | 0.69 | MEDIUM | 0.83 | HIGH | Attribution reweight (60%) |
| Confident Fabrication | 0.29 | LOW | 0.13 | LOW | Already caught |
| Style Mimic (wrong facts) | 0.56 | MEDIUM | 0.58 | MEDIUM | Known gap — NLI catches it |
| Honest Refusal | 0.13 | LOW | 1.00 | HIGH | Refusal pre-check |
| Pure Chitchat | 0.00 | LOW | 0.50 | MEDIUM | Chitchat pre-check |

3 of 5 original failures fixed. Run `python -m evals.hallucination_experiments` to reproduce.

### Remaining Gaps

- **Style mimic (Exp 3):** Factually wrong responses that reuse context vocabulary still score MEDIUM on the heuristic. The NLI claim verification layer is the mitigation — it checks entailment, not just word overlap.
- **Multi-hop reasoning:** Answers combining facts from multiple chunks score lower on attribution because no single chunk covers the full response.
- **NLI latency:** Claim verification adds inference time. Not enabled by default on every request.

---

## Cost Analysis

Estimated cost per 10-turn conversation by model, assuming average token usage observed in testing.

| Model | Est. Input Tokens (10 turns) | Est. Output Tokens (10 turns) | Est. Cost (USD) |
|-------|------------------------------|-------------------------------|-----------------|
| gpt-4o-mini | Pending | Pending | Pending |
| gpt-4o | Pending | Pending | Pending |
| gpt-4-turbo | Pending | Pending | Pending |
| claude-sonnet-4 | Pending | Pending | Pending |
| claude-3-haiku | Pending | Pending | Pending |
| llama3 (local) | Pending | Pending | $0.00 |

> Token counts depend on conversation complexity, number of tool calls, and whether summarization triggers. The estimates above use averages from the eval harness runs.

---

## Limitations & Known Issues

- **In-memory traces only.** Hallucination scores and retrieval metadata are returned in the API response but not persisted to a database or logging backend. There is no way to retroactively audit past responses.
- **No persistent tracing.** No integration with LangSmith, Langfuse, or any trace store. Debugging a bad response from yesterday means re-running the query.
- **Streaming is incomplete.** The `/chat/stream` endpoint exists but hallucination detection runs after full generation, so confidence scores are only available at the end of the stream, not incrementally.
- **No online learning.** The knowledge base is static. Guest corrections ("actually, the Mummy Resort pool closes at 8pm, not 10pm") are not fed back into the retrieval index.
- **Heuristic detector has a known gap.** The Tier 1 heuristic measures lexical grounding, not factual accuracy. Responses that reuse context vocabulary but state wrong facts score MEDIUM. The Tier 2 NLI verification mitigates this but adds latency and is not on by default.
- **Guardrails are rule-based.** InputGuard detects 13 injection patterns and redacts PII, but it's regex-based, not ML-based. Sophisticated adversarial attacks could bypass it.
- **Summarization is lossy.** The auto-summarization at 12 messages compresses context, which means specific details from early in a conversation (allergies, room preferences, accessibility needs) can be lost.
- **Eval harness tool-use pass rate is 0%.** Tool selection accuracy is 80%, but end-to-end tool execution in the eval harness fails consistently due to mock/integration boundary issues. This needs investigation.
- **Single-instance SQLite by default.** Cannot horizontally scale writes without switching to PostgreSQL.
- **Rate limiting is global, not per-user.** All clients share the same quota, so one heavy user can starve others.
