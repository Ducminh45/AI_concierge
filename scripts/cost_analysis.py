"""LLM cost comparison across all supported models with persistent tracking.

Results are appended to a JSONL history file so you can see how costs
change as you add models or update pricing.

Usage:
    python scripts/cost_analysis.py               # run analysis, save to JSONL
    python scripts/cost_analysis.py --compare-last # diff last 2 runs
    python scripts/cost_analysis.py --history      # show full history
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

from app.core.cost_tracker import _load_pricing, estimate_cost  # noqa: E402

HISTORY_PATH = PROJECT_ROOT / "reports" / "cost_analysis_history.jsonl"

DISPLAY_NAMES = {
    "gpt-4o": "GPT-4o",
    "gpt-4o-mini": "GPT-4o Mini",
    "gpt-4-turbo": "GPT-4 Turbo",
    "gpt-3.5-turbo": "GPT-3.5 Turbo",
    "claude-sonnet-4-20250514": "Claude Sonnet 4",
    "claude-3-5-sonnet-20241022": "Claude 3.5 Sonnet",
    "claude-3-haiku-20240307": "Claude 3 Haiku",
    "llama3": "Llama 3 (local)",
}


# ---------------------------------------------------------------------------
# Cost simulation
# ---------------------------------------------------------------------------


def simulate_conversation(model: str, turns: int) -> float:
    """Simulate a multi-turn conversation and return total cost in USD.

    Token model:
      - Turn 1 prompt: 200 tokens, growing by 40 per subsequent turn
      - Completion: 100 tokens per turn (constant)
    """
    total = 0.0
    for turn in range(turns):
        prompt_tokens = 200 + (turn * 40)
        completion_tokens = 100
        total += estimate_cost(model, prompt_tokens, completion_tokens)
    return total


def run_analysis() -> list[dict]:
    """Run cost analysis for all models. Returns per-model result dicts."""
    rows = []
    for model, (input_price, output_price) in _load_pricing().items():
        cost_10 = simulate_conversation(model, 10)
        cost_100 = simulate_conversation(model, 100)
        name = DISPLAY_NAMES.get(model, model)
        rows.append({
            "model": model,
            "display_name": name,
            "input_price": input_price,
            "output_price": output_price,
            "cost_10_turn": round(cost_10, 6),
            "cost_100_turn": round(cost_100, 6),
        })
    return rows


def print_analysis(rows: list[dict]) -> None:
    """Print the cost analysis table."""
    print("=" * 70)
    print("LLM COST ANALYSIS — Monster Resort Concierge")
    print("=" * 70)

    print("\n## Cost Comparison: 10-turn and 100-turn Conversations\n")
    print(
        "Token model: prompt starts at 200 tokens, "
        "+40/turn; completion = 100 tokens/turn.\n"
    )

    header = (
        "| Model | Input $/1M | Output $/1M "
        "| 10-turn cost | 100-turn cost |"
    )
    sep = (
        "|-------|----------:|-----------:"
        "|-------------:|--------------:|"
    )
    print(header)
    print(sep)

    for r in rows:
        inp_str = f"${r['input_price']:.2f}"  # noqa: E231
        out_str = f"${r['output_price']:.2f}"  # noqa: E231
        c10 = r["cost_10_turn"]
        c100 = r["cost_100_turn"]
        c10_str = f"${c10:.6f}" if c10 > 0 else "FREE"  # noqa: E231
        c100_str = f"${c100:.6f}" if c100 > 0 else "FREE"  # noqa: E231
        print(
            f"| {r['display_name']} | {inp_str} | {out_str} "
            f"| {c10_str} | {c100_str} |"
        )

    print("\n### Key Takeaways\n")

    paid = [(r["display_name"], r["cost_10_turn"]) for r in rows if r["cost_10_turn"] > 0]
    if paid:
        cheapest = min(paid, key=lambda x: x[1])
        most_exp = max(paid, key=lambda x: x[1])
        print(f"- Cheapest paid model (10 turns): **{cheapest[0]}** (${cheapest[1]:.6f})")  # noqa: E231
        print(f"- Most expensive (10 turns): **{most_exp[0]}** (${most_exp[1]:.6f})")  # noqa: E231

    print("- Local Llama 3 is free but requires GPU/CPU resources")

    total_prompt = sum(200 + (t * 40) for t in range(10))
    total_completion = 100 * 10
    print(
        f"\n10-turn totals: {total_prompt} prompt tokens + "
        f"{total_completion} completion tokens = "
        f"{total_prompt + total_completion} total tokens"
    )

    print("\nDone.")


# ---------------------------------------------------------------------------
# JSONL persistence
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


def save_run(rows: list[dict]) -> None:
    """Append this run to the JSONL history file."""
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)

    models = {}
    for r in rows:
        models[r["display_name"]] = {
            "cost_10": r["cost_10_turn"],
            "cost_100": r["cost_100_turn"],
        }

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_sha": _get_git_sha(),
        "num_models": len(rows),
        "models": models,
    }

    with open(HISTORY_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")

    print(f"\nRun appended to {HISTORY_PATH}")


def compare_last() -> None:
    """Print deltas between the two most recent runs."""
    if not HISTORY_PATH.exists():
        print("No cost analysis history found.")
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

    print("\n=== Cost Analysis Comparison (last two runs) ===")
    print(f"  Previous: {prev['git_sha']}  @ {prev['timestamp']}")  # noqa: E231
    print(f"  Current:  {curr['git_sha']}  @ {curr['timestamp']}")  # noqa: E231

    prev_models = prev.get("models", {})
    curr_models = curr.get("models", {})
    all_names = list(dict.fromkeys(
        list(prev_models.keys()) + list(curr_models.keys())
    ))

    print(f"\n  {'Model':<22} {'Prev 10t':>12} {'Curr 10t':>12} {'Delta':>10}")  # noqa: E231
    print(f"  {'─' * 22} {'─' * 12} {'─' * 12} {'─' * 10}")  # noqa: E231

    for name in all_names:
        p = prev_models.get(name, {}).get("cost_10", 0.0)
        c = curr_models.get(name, {}).get("cost_10", 0.0)
        delta = c - p
        if abs(delta) < 1e-8:
            d_str = "  —"
        else:
            sign = "+" if delta > 0 else ""
            d_str = f"{sign}${delta:.6f}"  # noqa: E231
        p_str = f"${p:.6f}" if p > 0 else "FREE"  # noqa: E231
        c_str = f"${c:.6f}" if c > 0 else "FREE"  # noqa: E231
        print(f"  {name:<22} {p_str:>12} {c_str:>12} {d_str:>10}")  # noqa: E231

    print()


def show_history() -> None:
    """Print all historical runs."""
    if not HISTORY_PATH.exists():
        print("No cost analysis history found.")
        return

    lines = HISTORY_PATH.read_text().strip().splitlines()
    print(f"\n=== Cost Analysis History ({len(lines)} runs) ===\n")

    for i, line in enumerate(lines, 1):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            print(f"  {i:>3}  [corrupted entry — skipped]")  # noqa: E231
            continue
        ts = entry["timestamp"][:10]
        sha = entry["git_sha"]
        n = entry["num_models"]
        print(f"  {i:>3}  {ts}  {sha}  {n} models")  # noqa: E231

    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="LLM cost analysis with persistent tracking"
    )
    parser.add_argument(
        "--compare-last", action="store_true",
        help="Print deltas between the two most recent runs",
    )
    parser.add_argument(
        "--history", action="store_true",
        help="Show full run history",
    )
    args = parser.parse_args()

    if args.compare_last:
        compare_last()
        return

    if args.history:
        show_history()
        return

    rows = run_analysis()
    print_analysis(rows)
    save_run(rows)


if __name__ == "__main__":
    main()
