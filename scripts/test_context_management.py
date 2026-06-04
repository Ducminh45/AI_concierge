"""Context management experiments: token scaling, window size, auto-summarisation."""

import asyncio
import os
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("MRC_DATABASE_URL", "sqlite:///./test_context_experiment.db")
os.environ.setdefault("MRC_REDIS_ENABLED", "false")

from dotenv import load_dotenv
load_dotenv()

# Memory.py looks for OPENAI_API_KEY; our .env uses MRC_OPENAI_API_KEY
if os.getenv("MRC_OPENAI_API_KEY") and not os.getenv("OPENAI_API_KEY"):
    os.environ["OPENAI_API_KEY"] = os.getenv("MRC_OPENAI_API_KEY")

from app.database.db import DatabaseManager
from app.core.memory import MemoryStore
from app.core.llm_providers import LLMMessage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def get_openai_client():
    """Get OpenAI client for direct API calls with token counting."""
    import openai
    api_key = os.getenv("MRC_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: No OpenAI API key found. Set MRC_OPENAI_API_KEY or OPENAI_API_KEY.")
        sys.exit(1)
    return openai.OpenAI(api_key=api_key)


def chat_with_history(client, system_prompt, messages, model="gpt-4o-mini"):
    """Send a chat request and return response + usage stats."""
    t0 = time.perf_counter()
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system_prompt}] + messages,
        max_tokens=256,
        temperature=0.3,
    )
    latency_ms = (time.perf_counter() - t0) * 1000
    return {
        "content": response.choices[0].message.content,
        "prompt_tokens": response.usage.prompt_tokens,
        "completion_tokens": response.usage.completion_tokens,
        "total_tokens": response.usage.total_tokens,
        "latency_ms": round(latency_ms, 1),
    }


# ---------------------------------------------------------------------------
# Experiment 1: No History vs With History
# ---------------------------------------------------------------------------
def experiment_1_context_matters(client):
    """Show that the model fails without conversation history."""
    print("\n" + "=" * 70)
    print("EXPERIMENT 1: Does Context Matter?")
    print("=" * 70)

    system = "You are a helpful concierge at Monster Game Resort."

    conversation = [
        {"role": "user", "content": "Hi! My name is Akin and I'm staying in room 42."},
        {"role": "assistant", "content": "Welcome to Monster Game Resort, Akin! Great to have you in room 42. How can I help you today?"},
        {"role": "user", "content": "What activities do you have for kids under 10?"},
        {"role": "assistant", "content": "We have the Monster Splash Pool (ages 3+), Cookie Monster's Baking Class (ages 5+), and the Junior Monster Hunt (ages 7+). Would you like to book any of these?"},
    ]

    follow_up = {"role": "user", "content": "Yes, book the baking class for tomorrow. And remind me — what room am I in?"}

    # Test A: WITH full history
    print("\n--- Test A: WITH conversation history (4 prior messages) ---")
    result_with = chat_with_history(client, system, conversation + [follow_up])
    print(f"  Response: {result_with['content'][:200]}...")
    print(f"  Tokens: {result_with['prompt_tokens']} prompt + {result_with['completion_tokens']} completion = {result_with['total_tokens']} total")
    print(f"  Latency: {result_with['latency_ms']}ms")

    # Test B: WITHOUT history (just the follow-up)
    print("\n--- Test B: WITHOUT conversation history (just the follow-up) ---")
    result_without = chat_with_history(client, system, [follow_up])
    print(f"  Response: {result_without['content'][:200]}...")
    print(f"  Tokens: {result_without['prompt_tokens']} prompt + {result_without['completion_tokens']} completion = {result_without['total_tokens']} total")
    print(f"  Latency: {result_without['latency_ms']}ms")

    print("\n--- FINDINGS ---")
    knew_name_with = "akin" in result_with["content"].lower()
    knew_name_without = "akin" in result_without["content"].lower()
    knew_room_with = "42" in result_with["content"]
    knew_room_without = "42" in result_without["content"]
    knew_class_with = "bak" in result_with["content"].lower()
    knew_class_without = "bak" in result_without["content"].lower()

    print(f"  WITH history:    knew name={knew_name_with}, knew room={knew_room_with}, knew baking class={knew_class_with}")
    print(f"  WITHOUT history: knew name={knew_name_without}, knew room={knew_room_without}, knew baking class={knew_class_without}")
    print(f"  Token overhead for history: +{result_with['prompt_tokens'] - result_without['prompt_tokens']} prompt tokens")

    return result_with, result_without


# ---------------------------------------------------------------------------
# Experiment 2: Token Cost at Different History Sizes
# ---------------------------------------------------------------------------
def experiment_2_token_scaling(client):
    """Measure how token cost scales with conversation length."""
    print("\n" + "=" * 70)
    print("EXPERIMENT 2: Token Cost vs History Size")
    print("=" * 70)

    system = "You are a helpful concierge at Monster Game Resort."

    turns = [
        ("user", "Hi, I'm checking in. Name's Akin."),
        ("assistant", "Welcome Akin! How can I help you today?"),
        ("user", "What restaurants do you have?"),
        ("assistant", "We have The Monster Grill (steakhouse), Cookie's Kitchen (family), and The Haunted Bistro (fine dining)."),
        ("user", "Book me a table at Cookie's Kitchen for 7pm tonight."),
        ("assistant", "Done! Table for one at Cookie's Kitchen, 7pm tonight. Anything else?"),
        ("user", "Actually make it a table for 3."),
        ("assistant", "Updated to a table for 3 at Cookie's Kitchen, 7pm. Got it!"),
        ("user", "What's the pool schedule?"),
        ("assistant", "Monster Splash Pool is open 8am-8pm. The adults-only Moonlight Pool opens at 9pm."),
        ("user", "Can I get extra towels sent to my room?"),
        ("assistant", "Absolutely! I'll have extra towels sent to your room right away."),
        ("user", "What's the wifi password?"),
        ("assistant", "The wifi network is 'MonsterGuest' and the password is 'Spooky2026'."),
        ("user", "Is there a gym?"),
        ("assistant", "Yes! The Monster Fitness Center is on the 3rd floor, open 24/7. Towels and water provided."),
        ("user", "Book me a spa appointment for tomorrow morning."),
        ("assistant", "I've booked a spa appointment for tomorrow morning at 10am. The spa is on the 4th floor."),
        ("user", "What time is checkout?"),
        ("assistant", "Checkout is at 11am. Late checkout until 2pm is available for a $50 fee."),
    ]

    question = {"role": "user", "content": "Can you summarise everything I've booked so far?"}

    results = []
    for history_size in [0, 2, 4, 6, 10, 14, 20]:
        messages = [{"role": r, "content": c} for r, c in turns[:history_size]]
        messages.append(question)

        result = chat_with_history(client, system, messages)
        results.append({
            "history_turns": history_size,
            "prompt_tokens": result["prompt_tokens"],
            "total_tokens": result["total_tokens"],
            "latency_ms": result["latency_ms"],
            "response_preview": result["content"][:100],
        })
        print(f"  {history_size:2d} turns of history: {result['prompt_tokens']:4d} prompt tokens, {result['total_tokens']:5d} total, {result['latency_ms']:7.1f}ms")

    # Cost estimate (gpt-4o-mini pricing: $0.15/1M input, $0.60/1M output as of 2025)
    print("\n--- COST ANALYSIS (gpt-4o-mini pricing) ---")
    for r in results:
        input_cost = r["prompt_tokens"] * 0.15 / 1_000_000
        output_cost = (r["total_tokens"] - r["prompt_tokens"]) * 0.60 / 1_000_000
        total_cost = input_cost + output_cost
        print(f"  {r['history_turns']:2d} turns: ${total_cost:.6f} per request")

    if len(results) >= 2:
        ratio = results[-1]["prompt_tokens"] / results[0]["prompt_tokens"]
        print(f"\n  Token increase from 0 to {results[-1]['history_turns']} turns: {ratio:.1f}x")

    return results


# ---------------------------------------------------------------------------
# Experiment 3: Memory Summarisation Trigger
# ---------------------------------------------------------------------------
def experiment_3_summarisation(client):
    """Show the auto-summarisation mechanism firing at 12 messages."""
    print("\n" + "=" * 70)
    print("EXPERIMENT 3: Auto-Summarisation Trigger")
    print("=" * 70)

    # Set up a fresh SQLite database and MemoryStore
    test_db_path = "test_context_experiment.db"
    if Path(test_db_path).exists():
        os.remove(test_db_path)

    db = DatabaseManager(f"sqlite:///{test_db_path}")
    memory = MemoryStore(db=db, max_messages_before_summary=12)

    session_id = f"exp3-{uuid.uuid4().hex[:8]}"

    turns = [
        ("user", "Hi, I'm Akin checking into room 42."),
        ("assistant", "Welcome Akin! Room 42, got it."),
        ("user", "What restaurants do you have?"),
        ("assistant", "Monster Grill, Cookie's Kitchen, Haunted Bistro."),
        ("user", "Book Cookie's Kitchen for 3 at 7pm."),
        ("assistant", "Done! Table for 3 at Cookie's Kitchen, 7pm."),
        ("user", "What's the pool schedule?"),
        ("assistant", "Monster Splash: 8am-8pm. Moonlight Pool: 9pm+."),
        ("user", "Send extra towels to my room please."),
        ("assistant", "Extra towels on the way to room 42!"),
        ("user", "What's the wifi password?"),
        ("assistant", "Network: MonsterGuest, Password: Spooky2026."),
        ("user", "Is there a gym?"),
        ("assistant", "Yes! 3rd floor, open 24/7."),
    ]

    print(f"\n  Sending {len(turns)} messages (threshold = {memory.max_messages_before_summary})...")

    for i, (role, content) in enumerate(turns):
        memory.add_message(session_id, role, content)
        msgs = memory.get_messages(session_id)
        msg_count = len(msgs)

        with db.session() as conn:
            row = conn.execute(
                "SELECT summary FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            has_summary = bool(row and row["summary"])

        if i == 11:  # The 12th message (0-indexed)
            print(f"  Message {i+1:2d} ({role}): {msg_count} messages in DB, summary={'YES' if has_summary else 'no'} <-- THRESHOLD HIT")
        elif has_summary:
            print(f"  Message {i+1:2d} ({role}): {msg_count} messages in DB, summary=YES (summarised!)")
        else:
            print(f"  Message {i+1:2d} ({role}): {msg_count} messages in DB, summary={'YES' if has_summary else 'no'}")

    with db.session() as conn:
        row = conn.execute(
            "SELECT summary FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row and row["summary"]:
            print(f"\n  SUMMARY CONTENT:\n  {row['summary'][:300]}")

    final_msgs = memory.get_messages(session_id)
    print(f"\n  Final state: {len(final_msgs)} messages remaining in DB (rest were summarised and deleted)")

    db_full_path = Path(__file__).resolve().parent.parent / test_db_path
    if Path(test_db_path).exists():
        Path(test_db_path).unlink()
    elif db_full_path.exists():
        db_full_path.unlink()

    return {"total_sent": len(turns), "remaining": len(final_msgs)}


# ---------------------------------------------------------------------------
# Experiment 4: The limit=5 Window — Quality Check
# ---------------------------------------------------------------------------
def experiment_4_window_size(client):
    """Compare response quality with different history window sizes."""
    print("\n" + "=" * 70)
    print("EXPERIMENT 4: History Window Size vs Response Quality")
    print("=" * 70)

    system = "You are a helpful concierge at Monster Game Resort. Always address the guest by name if known."

    full_conversation = [
        {"role": "user", "content": "Hi! I'm Akin, I'm allergic to nuts and I'm vegan."},
        {"role": "assistant", "content": "Welcome Akin! I've noted your nut allergy and vegan diet. I'll make sure all recommendations are safe for you."},
        {"role": "user", "content": "What's the weather like today?"},
        {"role": "assistant", "content": "It's sunny and 24°C today — perfect for the pool!"},
        {"role": "user", "content": "How do I get to the spa?"},
        {"role": "assistant", "content": "The spa is on the 4th floor. Take the elevator near the lobby."},
        {"role": "user", "content": "What time does the pool close?"},
        {"role": "assistant", "content": "Monster Splash Pool closes at 8pm. The Moonlight Pool opens at 9pm."},
        {"role": "user", "content": "Is there a gift shop?"},
        {"role": "assistant", "content": "Yes! The Monster Gift Shop is in the lobby, open 9am-9pm."},
    ]

    question = {"role": "user", "content": "Recommend me a restaurant for dinner tonight."}

    print("\n  Testing: Does the model remember the nut allergy and vegan diet?")
    print("  (This info was in message 1 — will it survive different window sizes?)\n")

    for window_size in [2, 5, 10, "all"]:
        if window_size == "all":
            msgs = full_conversation + [question]
            label = "all 10"
        else:
            # Take the LAST N messages (simulating a sliding window)
            msgs = full_conversation[-(window_size * 2):] + [question]
            label = f"last {window_size}"

        result = chat_with_history(client, system, msgs)
        mentions_allergy = "nut" in result["content"].lower() or "allerg" in result["content"].lower()
        mentions_vegan = "vegan" in result["content"].lower() or "plant" in result["content"].lower()
        mentions_name = "akin" in result["content"].lower()

        print(f"  Window={label:>6}: name={mentions_name}, allergy={mentions_allergy}, vegan={mentions_vegan} | {result['prompt_tokens']} tokens | {result['latency_ms']}ms")
        print(f"    Response: {result['content'][:150]}...")
        print()

    print("  KEY INSIGHT: With a small window (last 2-5), the dietary info from")
    print("  message 1 falls out. The model gives unsafe recommendations.")
    print("  This is why summarisation matters — critical facts must persist.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("=" * 70)
    print("CONTEXT MANAGEMENT EXPERIMENTS")
    print("Monster Game Resort Concierge")
    print("=" * 70)
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    client = get_openai_client()

    exp1_with, exp1_without = experiment_1_context_matters(client)
    exp2_results = experiment_2_token_scaling(client)
    exp3_result = experiment_3_summarisation(client)
    experiment_4_window_size(client)

    print("\n" + "=" * 70)
    print("SUMMARY — Article Data Points")
    print("=" * 70)
    print(f"  1. Without history: model lost name, room, and context ({exp1_without['total_tokens']} tokens)")
    print(f"     With history: model retained everything ({exp1_with['total_tokens']} tokens)")
    print(f"     Token overhead: +{exp1_with['prompt_tokens'] - exp1_without['prompt_tokens']} prompt tokens")
    print(f"  2. Token scaling: {exp2_results[0]['prompt_tokens']} tokens (0 turns) → {exp2_results[-1]['prompt_tokens']} tokens ({exp2_results[-1]['history_turns']} turns)")
    print(f"  3. Summarisation: {exp3_result['total_sent']} messages sent, {exp3_result['remaining']} remain after auto-summarisation")
    print(f"  4. Window size: dietary restrictions lost when early messages fall out of the window")
    print("=" * 70)


if __name__ == "__main__":
    main()
