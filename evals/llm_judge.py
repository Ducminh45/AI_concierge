"""LLM-as-Judge evaluator using GPT-4o-mini for (question, context, answer) scoring.

Scores each triple on correctness, groundedness, and relevance (1-5 scale)
with chain-of-thought reasoning.  Results are persisted to JSONL for
longitudinal tracking.

Usage:
    python -m evals.llm_judge                       # run 5 built-in cases
    python -m evals.llm_judge --compare-heuristic   # also run heuristic detector
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

HISTORY_PATH = PROJECT_ROOT / "reports" / "llm_judge_history.jsonl"

# ---------------------------------------------------------------------------
# Scoring prompt / rubric
# ---------------------------------------------------------------------------

JUDGE_SYSTEM_PROMPT = """\
You are an impartial evaluation judge.  You will be given a QUESTION, one or \
more CONTEXT passages, and an ANSWER.  Your job is to rate the ANSWER on \
three dimensions using the rubric below.

### Scoring rubric (use integer scores 1-5)

**correctness** - Is the answer factually correct given the context?
  1: Completely wrong or fabricated
  2: Mostly wrong with minor correct elements
  3: Partially correct but significant gaps or errors
  4: Mostly correct with minor issues
  5: Fully correct and accurate

**groundedness** - Is every claim in the answer supported by the provided context?
  1: No claims are supported; entirely fabricated details
  2: Most claims are unsupported; heavy fabrication
  3: Some claims are supported but significant unsupported material
  4: Nearly all claims are supported; minor extrapolation
  5: Every claim is directly supported by the context

**relevance** - Does the answer address the question?
  1: Completely off-topic
  2: Tangentially related but does not answer the question
  3: Partially addresses the question
  4: Mostly addresses the question with minor gaps
  5: Directly and fully addresses the question

### Special cases
- If the answer is an honest refusal (e.g. "I don't have that information"), \
score correctness=5, groundedness=5, relevance=4.  Honest refusals are safe.
- If there is no context provided (e.g. chitchat), you may score groundedness \
as 3 (neutral) since grounding is not applicable.

### Response format
Return ONLY valid JSON with these exact keys:
{
  "correctness": <int 1-5>,
  "groundedness": <int 1-5>,
  "relevance": <int 1-5>,
  "reasoning": "<brief explanation of your scores>"
}
"""


def _build_user_message(
    question: str,
    answer: str,
    contexts: list[str],
) -> str:
    """Format the user message containing the triple to evaluate."""
    if contexts:
        ctx_block = "\n\n".join(
            f"[Context {i + 1}]: {ctx}" for i, ctx in enumerate(contexts)
        )
    else:
        ctx_block = "(No context provided)"

    return (
        f"QUESTION:\n{question}\n\n"  # noqa: E231
        f"CONTEXT:\n{ctx_block}\n\n"  # noqa: E231
        f"ANSWER:\n{answer}"  # noqa: E231
    )


# ---------------------------------------------------------------------------
# Core judge functions
# ---------------------------------------------------------------------------


def judge_response(
    question: str,
    answer: str,
    contexts: list[str],
    model: str = "gpt-4o-mini",
) -> Optional[Dict[str, Any]]:
    """Call GPT-4o-mini to score a single (question, context, answer) triple.

    Returns dict with keys: correctness, groundedness, relevance, reasoning.
    Returns None on API failure (with a warning printed to stderr).
    """
    try:
        import openai
    except ImportError:
        warnings.warn(
            "openai package not installed. Run: pip install openai",
            stacklevel=2,
        )
        return None

    client = openai.OpenAI()

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": _build_user_message(question, answer, contexts),
                },
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
        )
    except Exception as exc:
        warnings.warn(
            f"LLM judge API call failed: {exc}",
            stacklevel=2,
        )
        return None

    raw = response.choices[0].message.content or ""

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        warnings.warn(
            f"LLM judge returned invalid JSON: {raw[:200]}",
            stacklevel=2,
        )
        return None

    # Validate and clamp scores
    result: Dict[str, Any] = {"reasoning": str(parsed.get("reasoning", ""))}
    for key in ("correctness", "groundedness", "relevance"):
        val = parsed.get(key)
        try:
            val = int(val)
        except (TypeError, ValueError):
            val = 0
        result[key] = max(1, min(5, val))

    return result


def judge_batch(
    items: List[Dict[str, Any]],
    model: str = "gpt-4o-mini",
) -> Dict[str, Any]:
    """Score a batch of (question, contexts, answer) dicts.

    Each item must have keys: question, contexts, answer.

    Returns:
        {
            "results": [<per-item result or None>, ...],
            "aggregated": {
                "mean_correctness": float,
                "mean_groundedness": float,
                "mean_relevance": float,
                "num_scored": int,
                "num_failed": int,
            }
        }
    """
    results: List[Optional[Dict[str, Any]]] = []

    for item in items:
        r = judge_response(
            question=item["question"],
            answer=item["answer"],
            contexts=item.get("contexts", []),
            model=model,
        )
        results.append(r)

    scored = [r for r in results if r is not None]
    num_scored = len(scored)
    num_failed = len(results) - num_scored

    if num_scored > 0:
        aggregated = {
            "mean_correctness": sum(r["correctness"] for r in scored) / num_scored,
            "mean_groundedness": sum(r["groundedness"] for r in scored) / num_scored,
            "mean_relevance": sum(r["relevance"] for r in scored) / num_scored,
            "num_scored": num_scored,
            "num_failed": num_failed,
        }
    else:
        aggregated = {
            "mean_correctness": 0.0,
            "mean_groundedness": 0.0,
            "mean_relevance": 0.0,
            "num_scored": 0,
            "num_failed": num_failed,
        }

    return {"results": results, "aggregated": aggregated}


# ---------------------------------------------------------------------------
# Built-in test cases (mirror hallucination_experiments.py scenarios)
# ---------------------------------------------------------------------------

TEST_CASES = [
    {
        "id": 1,
        "name": "Faithful Paraphrase",
        "question": "What time is check-in?",
        "answer": (
            "Check-in starts at 3 PM across most properties. "
            "If you arrive early, we can try to get your lair ready sooner. "
            "For our nocturnal friends, moonlight arrivals can be arranged."
        ),
        "contexts": [
            "Check-in is from 3:00 PM. Early check-in is available "
            "based on lair readiness.",
            "For nocturnal guests, we can arrange 'moonlight arrival' "
            "with prior notice.",
            "Checkout is by 11:00 AM. Late checkout may incur a small "
            "broomstick fee.",
        ],
        "expect": "high scores across the board",
    },
    {
        "id": 2,
        "name": "Confident Fabrication",
        "question": "What are the spa treatments at Werewolf Lodge?",
        "answer": (
            "The Werewolf Lodge offers a Crystal Moonbeam Facial, "
            "a Deep Forest Mud Wrap sourced from enchanted Scottish clay, "
            "and an exclusive Howling Harmony Sound Bath priced at "
            "200 Monster Tokens. "
            "Sessions run from midnight to 4 AM in the underground grotto."
        ),
        "contexts": [
            "Spa Services: Lunar Wellness Center. Full-Body Fur Grooming "
            "& Conditioning. Claw Sharpening & Polish. Moonstone Hot "
            "Stone Massage. Howling Therapy Sessions (soundproof booths). "
            "Post-Transformation Recovery Treatment. Silver-Free "
            "Aromatherapy.",
            "Location: Scottish Highlands, deep in the misty moorlands.",
        ],
        "expect": "low groundedness (fabricated treatment names)",
    },
    {
        "id": 3,
        "name": "Style Mimic",
        "question": "Tell me about Castle Frankenstein's room types.",
        "answer": (
            "Castle Frankenstein offers three luxurious room types: "
            "the Thunderclap Suite with complimentary beakers, "
            "the Igor's Quarters featuring a private lightning balcony, "
            "and the Monster Penthouse with 180-degree views. "
            "All rooms include surge protectors and rubber flooring."
        ),
        "contexts": [
            "Room Types: Galvanic Suites with adjustable voltage "
            "(10-1000V). Laboratory Lofts: Mad scientist-themed with "
            "complimentary beakers. Bolted Bedchambers: Premium suites "
            "with neck-bolt charging stations. Tesla Tower Penthouse: "
            "360-degree views, unlimited electricity.",
            "All rooms equipped with lightning rods & surge protectors.",
        ],
        "expect": "low correctness (wrong room names despite right style)",
    },
    {
        "id": 4,
        "name": "Honest Refusal",
        "question": "Do you offer helicopter transfers from the airport?",
        "answer": (
            "I don't have specific information about helicopter transfers. "
            "I'd recommend contacting our reservations team at 1-800-MONSTER "
            "for transportation arrangements."
        ),
        "contexts": [
            "Hearse Shuttle Service (all properties). Bat Flight Charters "
            "(Vampire Manor specialty). Sandstorm Portals (Mummy Resort). "
            "Coffin Express Delivery.",
        ],
        "expect": "high scores (safe honest refusal)",
    },
    {
        "id": 5,
        "name": "Pure Chitchat",
        "question": "Hello, how are you?",
        "answer": (
            "Welcome to Monster Resort! I'm doing wonderfully, thank you "
            "for asking. How can I help you plan your supernatural getaway "
            "today?"
        ),
        "contexts": [],
        "expect": "neutral groundedness (N/A), high relevance",
    },
]


# ---------------------------------------------------------------------------
# Heuristic comparison helper
# ---------------------------------------------------------------------------


def _run_heuristic(test_case: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Run the heuristic hallucination detector on a test case."""
    try:
        from app.validation.hallucination import HallucinationDetector

        detector = HallucinationDetector()
        result = detector.score_response(
            test_case["answer"], test_case["contexts"]
        )
        d = result.to_dict()
        return {
            "level": d["level"],
            "overall_score": d["overall_score"],
            "overlap": d["context_overlap_score"],
            "semantic": d["semantic_similarity_score"],
            "attribution": d["source_attribution_score"],
        }
    except Exception as exc:
        warnings.warn(f"Heuristic detector failed: {exc}", stacklevel=2)
        return None


# ---------------------------------------------------------------------------
# JSONL persistence
# ---------------------------------------------------------------------------


def _get_git_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
        )
        return result.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def save_run(
    results: List[Optional[Dict[str, Any]]],
    test_cases: List[Dict[str, Any]],
    heuristic_results: Optional[List[Optional[Dict[str, Any]]]] = None,
) -> None:
    """Append this run to the JSONL history file."""
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)

    per_case: Dict[str, Any] = {}
    for tc, r in zip(test_cases, results):
        entry: Dict[str, Any] = {"judge": r}
        if heuristic_results is not None:
            idx = test_cases.index(tc)
            entry["heuristic"] = heuristic_results[idx]
        per_case[tc["name"]] = entry

    scored = [r for r in results if r is not None]
    num_scored = len(scored)

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_sha": _get_git_sha(),
        "num_cases": len(test_cases),
        "num_scored": num_scored,
        "num_failed": len(test_cases) - num_scored,
        "cases": per_case,
    }

    if num_scored > 0:
        record["mean_correctness"] = round(
            sum(r["correctness"] for r in scored) / num_scored, 2
        )
        record["mean_groundedness"] = round(
            sum(r["groundedness"] for r in scored) / num_scored, 2
        )
        record["mean_relevance"] = round(
            sum(r["relevance"] for r in scored) / num_scored, 2
        )

    with open(HISTORY_PATH, "a") as f:
        f.write(json.dumps(record) + "\n")

    print(f"\nRun appended to {HISTORY_PATH}")


# ---------------------------------------------------------------------------
# CLI display
# ---------------------------------------------------------------------------


def print_results(
    test_cases: List[Dict[str, Any]],
    results: List[Optional[Dict[str, Any]]],
    heuristic_results: Optional[List[Optional[Dict[str, Any]]]] = None,
) -> None:
    """Print a formatted table of LLM judge results."""
    print("=" * 72)
    print("LLM-AS-JUDGE EVALUATION (GPT-4o-mini)")
    print("=" * 72)

    scored = []
    for tc, r in zip(test_cases, results):
        print(f"\n{'─' * 72}")
        print(f"  CASE {tc['id']}: {tc['name']}")
        print(f"  Expected: {tc['expect']}")
        print(f"{'─' * 72}")

        if r is None:
            print("  [FAILED] Could not get LLM judge score")
        else:
            scored.append(r)
            print(
                f"  correctness={r['correctness']}  "
                f"groundedness={r['groundedness']}  "
                f"relevance={r['relevance']}"
            )
            print(f"  reasoning: {r['reasoning']}")

        if heuristic_results is not None:
            idx = test_cases.index(tc)
            hr = heuristic_results[idx]
            if hr is not None:
                print(
                    f"  [heuristic] level={hr['level']}  "  # noqa: E231
                    f"score={hr['overall_score']:.4f}  "  # noqa: E231
                    f"overlap={hr['overlap']:.4f}  "  # noqa: E231
                    f"semantic={hr['semantic']:.4f}  "  # noqa: E231
                    f"attribution={hr['attribution']:.4f}"  # noqa: E231
                )
            else:
                print("  [heuristic] FAILED")

    # Summary
    print(f"\n{'=' * 72}")
    if scored:
        n = len(scored)
        mc = sum(r["correctness"] for r in scored) / n
        mg = sum(r["groundedness"] for r in scored) / n
        mr = sum(r["relevance"] for r in scored) / n
        print(
            f"  Scored {n}/{len(test_cases)} cases  |  "  # noqa: E221,E222,E231
            f"mean correctness={mc:.1f}  "  # noqa: E231
            f"groundedness={mg:.1f}  "  # noqa: E231
            f"relevance={mr:.1f}"  # noqa: E231
        )
    else:
        print("  No cases scored successfully.")
    print("=" * 72)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="LLM-as-Judge evaluator for RAG answer quality"
    )
    parser.add_argument(
        "--compare-heuristic",
        action="store_true",
        help="Also run the heuristic hallucination detector for comparison",
    )
    parser.add_argument(
        "--model",
        default="gpt-4o-mini",
        help="OpenAI model to use as judge (default: gpt-4o-mini)",
    )
    args = parser.parse_args()

    print(f"Running LLM judge with model={args.model} ...")

    # Run LLM judge on all test cases
    results: List[Optional[Dict[str, Any]]] = []
    for tc in TEST_CASES:
        r = judge_response(
            question=tc["question"],
            answer=tc["answer"],
            contexts=tc["contexts"],
            model=args.model,
        )
        results.append(r)

    # Optionally run heuristic detector
    heuristic_results: Optional[List[Optional[Dict[str, Any]]]] = None
    if args.compare_heuristic:
        print("Running heuristic detector for comparison ...")
        heuristic_results = [_run_heuristic(tc) for tc in TEST_CASES]

    print_results(TEST_CASES, results, heuristic_results)
    save_run(results, TEST_CASES, heuristic_results)


if __name__ == "__main__":
    main()
