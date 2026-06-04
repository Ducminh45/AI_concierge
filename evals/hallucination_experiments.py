"""Hallucination detection experiments with persistent result tracking.

Each experiment probes a specific weakness in the detector. Results are
appended to a JSONL history file so you can track how changes to the
detector affect scores over time.

Usage:
    python -m evals.hallucination_experiments          # run all, save to JSONL
    python -m evals.hallucination_experiments --compare-last  # diff last 2 runs
    python -m evals.hallucination_experiments --history       # show full history
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.validation.hallucination import HallucinationDetector  # noqa: E402

HISTORY_PATH = PROJECT_ROOT / "reports" / "hallucination_history.jsonl"

# ---------------------------------------------------------------------------
# Experiment definitions
# ---------------------------------------------------------------------------

EXPERIMENTS = [
    {
        "id": 1,
        "name": "Faithful Paraphrase",
        "expected_level": "HIGH",
        "query": "What time is check-in?",
        "response": (
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
    },
    {
        "id": 2,
        "name": "Confident Fabrication",
        "expected_level": "LOW",
        "query": "What are the spa treatments at Werewolf Lodge?",
        "response": (
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
    },
    {
        "id": 3,
        "name": "Style Mimic",
        "expected_level": "LOW",
        "query": "Tell me about Castle Frankenstein's room types.",
        "response": (
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
    },
    {
        "id": 4,
        "name": "Honest Refusal",
        "expected_level": "HIGH",
        "query": "Do you offer helicopter transfers from the airport?",
        "response": (
            "I don't have specific information about helicopter transfers. "
            "I'd recommend contacting our reservations team at 1-800-MONSTER "
            "for transportation arrangements."
        ),
        "contexts": [
            "Hearse Shuttle Service (all properties). Bat Flight Charters "
            "(Vampire Manor specialty). Sandstorm Portals (Mummy Resort). "
            "Coffin Express Delivery.",
        ],
    },
    {
        "id": 5,
        "name": "Pure Chitchat",
        "expected_level": "MEDIUM",
        "query": "Hello, how are you?",
        "response": (
            "Welcome to Monster Resort! I'm doing wonderfully, thank you "
            "for asking. How can I help you plan your supernatural getaway "
            "today?"
        ),
        "contexts": [],
    },
]


# ---------------------------------------------------------------------------
# Run experiments
# ---------------------------------------------------------------------------


def _get_git_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True,
        )
        return result.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def run_experiments(
    detector: HallucinationDetector,
) -> list[dict]:
    """Run all experiments and return per-experiment result dicts."""
    results = []
    for exp in EXPERIMENTS:
        r = detector.score_response(exp["response"], exp["contexts"])
        d = r.to_dict()
        results.append({
            "id": exp["id"],
            "name": exp["name"],
            "expected_level": exp["expected_level"],
            "actual_level": d["level"],
            "overall_score": d["overall_score"],
            "overlap": d["context_overlap_score"],
            "semantic": d["semantic_similarity_score"],
            "attribution": d["source_attribution_score"],
            "note": d.get("note"),
            "match": exp["expected_level"] == d["level"],
        })
    return results


def print_results(results: list[dict]) -> None:
    """Print a table of experiment results."""
    print("=" * 72)
    print("HALLUCINATION DETECTOR EXPERIMENTS")
    print("=" * 72)

    matches = 0
    for r in results:
        mark = "OK" if r["match"] else "MISMATCH"
        matches += int(r["match"])
        print(f"\n{'─' * 72}")
        print(f"  EXP {r['id']}: {r['name']}  [{mark}]")
        print(f"{'─' * 72}")
        print(
            f"  Expected: {r['expected_level']:<8} "  # noqa: E231
            f"Actual: {r['actual_level']:<8} "  # noqa: E231
            f"Score: {r['overall_score']:.4f}"  # noqa: E231
        )
        print(
            f"  overlap={r['overlap']:.4f}  "  # noqa: E231
            f"semantic={r['semantic']:.4f}  "  # noqa: E231
            f"attribution={r['attribution']:.4f}"  # noqa: E231
        )
        if r["note"]:
            print(f"  note: {r['note']}")

    print(f"\n{'=' * 72}")
    print(f"  {matches}/{len(results)} experiments match expected level")
    print("=" * 72)


# ---------------------------------------------------------------------------
# JSONL persistence
# ---------------------------------------------------------------------------


def save_run(results: list[dict]) -> None:
    """Append this run to the JSONL history file."""
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)

    per_exp = {}
    for r in results:
        per_exp[r["name"]] = {
            "level": r["actual_level"],
            "score": r["overall_score"],
            "match": r["match"],
        }

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_sha": _get_git_sha(),
        "num_experiments": len(results),
        "num_matched": sum(1 for r in results if r["match"]),
        "experiments": per_exp,
    }

    with open(HISTORY_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")

    print(f"\nRun appended to {HISTORY_PATH}")


def compare_last() -> None:
    """Print metric deltas between the two most recent runs."""
    if not HISTORY_PATH.exists():
        print("No hallucination history found.")
        return

    lines = HISTORY_PATH.read_text().strip().splitlines()
    if len(lines) < 2:
        print("Need at least 2 runs in history to compare.")
        return

    try:
        prev = json.loads(lines[-2])
        curr = json.loads(lines[-1])
    except json.JSONDecodeError:
        print("Error: corrupted history entries. Re-run to generate fresh data.")
        return

    print("\n=== Hallucination Experiment Comparison ===")
    print(
        f"  Previous: {prev['git_sha']}  "  # noqa: E241
        f"@ {prev['timestamp']}"
    )
    print(
        f"  Current:  {curr['git_sha']}  "  # noqa: E241
        f"@ {curr['timestamp']}"
    )
    print(
        f"\n  Match rate: "
        f"{prev['num_matched']}/{prev['num_experiments']} -> "
        f"{curr['num_matched']}/{curr['num_experiments']}"
    )

    print(f"\n  {'Experiment':<25} {'Prev':>12} {'Curr':>12} {'Delta':>10}")  # noqa: E231
    print(f"  {'─' * 25} {'─' * 12} {'─' * 12} {'─' * 10}")  # noqa: E231

    prev_exps = prev.get("experiments", {})
    curr_exps = curr.get("experiments", {})
    all_names = list(dict.fromkeys(
        list(prev_exps.keys()) + list(curr_exps.keys())
    ))

    for name in all_names:
        p = prev_exps.get(name, {})
        c = curr_exps.get(name, {})
        p_score = p.get("score", 0.0)
        c_score = c.get("score", 0.0)
        delta = c_score - p_score

        p_label = f"{p.get('level', '—'):>5} {p_score:.4f}"  # noqa: E231
        c_label = f"{c.get('level', '—'):>5} {c_score:.4f}"  # noqa: E231

        if abs(delta) < 1e-6:
            d_label = "  —"
        elif delta > 0:
            d_label = f" +{delta:.4f}"  # noqa: E231
        else:
            d_label = f" {delta:.4f}"  # noqa: E231

        print(f"  {name:<25} {p_label:>12} {c_label:>12} {d_label:>10}")  # noqa: E231

    print()


def show_history() -> None:
    """Print all historical runs as a timeline."""
    if not HISTORY_PATH.exists():
        print("No hallucination history found.")
        return

    lines = HISTORY_PATH.read_text().strip().splitlines()
    print(f"\n=== Hallucination Experiment History ({len(lines)} runs) ===\n")
    print(
        f"  {'#':>3}  {'Date':>10}  {'SHA':>8}  "  # noqa: E231
        f"{'Matched':>8}  Scores"  # noqa: E231
    )
    print(f"  {'─' * 3}  {'─' * 10}  {'─' * 8}  {'─' * 8}  {'─' * 30}")  # noqa: E231

    for i, line in enumerate(lines, 1):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            print(f"  {i:>3}  [corrupted entry — skipped]")  # noqa: E231
            continue
        ts = entry["timestamp"][:10]
        sha = entry["git_sha"]
        matched = f"{entry['num_matched']}/{entry['num_experiments']}"

        scores = []
        for name, data in entry.get("experiments", {}).items():
            short = name[:3]
            scores.append(f"{short}={data['score']:.2f}")  # noqa: E231
        score_str = "  ".join(scores)

        print(f"  {i:>3}  {ts}  {sha:>8}  {matched:>8}  {score_str}")  # noqa: E231

    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run hallucination detection experiments"
    )
    parser.add_argument(
        "--compare-last",
        action="store_true",
        help="Print deltas between the two most recent runs",
    )
    parser.add_argument(
        "--history",
        action="store_true",
        help="Show full run history",
    )
    args = parser.parse_args()

    if args.compare_last:
        compare_last()
        return

    if args.history:
        show_history()
        return

    detector = HallucinationDetector()
    results = run_experiments(detector)
    print_results(results)
    save_run(results)


if __name__ == "__main__":
    main()
