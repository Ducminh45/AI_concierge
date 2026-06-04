"""Converts concierge_qa.json into MLX chat-format JSONL files for LoRA fine-tuning."""

import json
import random
import sys
from pathlib import Path

# Resolve project root relative to this script
PROJECT_ROOT = Path(__file__).resolve().parent.parent
QA_PATH = PROJECT_ROOT / "data" / "concierge_qa.json"
OUTPUT_DIR = PROJECT_ROOT / "data" / "finetune"

SYSTEM_PROMPT = (
    "You are the 'Grand Chamberlain' of the Monster Resort, an elegant and sophisticated "
    "AI concierge serving six supernatural properties: The Mummy Resort & Tomb-Service, "
    "The Werewolf Lodge: Moon & Moor, Castle Frankenstein: High Voltage Luxury, "
    "Vampire Manor: Eternal Night Inn, Zombie Bed & Breakfast: Bites & Beds, and "
    "Ghostly B&B: Spectral Stay. Answer guest questions with gothic flair, vivid language, "
    "and accurate resort knowledge. Be helpful, atmospheric, and precise."
)

TRAIN_SPLIT = 0.8


def load_qa_data(path: Path) -> list:
    """Load the Q&A dataset from JSON."""
    if not path.exists():
        print(f"ERROR: Dataset not found at {path}")
        print()
        print("Generate it first:")
        print("  python scripts/generate_synthetic_dataset.py --output data/concierge_qa.json")
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not data:
        print(f"ERROR: Dataset at {path} is empty.")
        sys.exit(1)

    return data


def convert_to_chat_format(qa_pairs: list) -> list:
    """Convert instruction/output pairs to MLX chat message format."""
    formatted = []
    skipped = 0

    for pair in qa_pairs:
        question = pair.get("instruction", "").strip()
        answer = pair.get("output", "").strip()

        if not question or not answer:
            skipped += 1
            continue

        # If there's an input field, append it to the question
        input_text = pair.get("input", "").strip()
        if input_text:
            question = f"{question}\n{input_text}"

        entry = {
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": question},
                {"role": "assistant", "content": answer},
            ]
        }
        formatted.append(entry)

    if skipped:
        print(f"  Skipped {skipped} pairs with empty question or answer")

    return formatted


def write_jsonl(data: list, path: Path):
    """Write a list of dicts as a JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for entry in data:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main():
    print("=" * 60)
    print("  Monster Resort -- Prepare Fine-Tuning Data")
    print("=" * 60)
    print()

    # Load
    print(f"Loading Q&A data from {QA_PATH}")
    qa_data = load_qa_data(QA_PATH)
    print(f"  Loaded {len(qa_data)} Q&A pairs")

    # Convert
    print("Converting to MLX chat format...")
    formatted = convert_to_chat_format(qa_data)
    print(f"  Converted {len(formatted)} pairs")

    # Shuffle deterministically
    random.seed(42)
    random.shuffle(formatted)

    # Split
    split_idx = int(len(formatted) * TRAIN_SPLIT)
    train_data = formatted[:split_idx]
    valid_data = formatted[split_idx:]

    # Write
    train_path = OUTPUT_DIR / "train.jsonl"
    valid_path = OUTPUT_DIR / "valid.jsonl"

    print(f"Writing training data to {train_path}")
    write_jsonl(train_data, train_path)

    print(f"Writing validation data to {valid_path}")
    write_jsonl(valid_data, valid_path)

    # Stats
    print()
    print("=" * 60)
    print("  Stats")
    print("=" * 60)
    print(f"  Total pairs:      {len(formatted)}")
    print(f"  Training set:     {len(train_data)} ({TRAIN_SPLIT * 100:.0f}%)")  # noqa: E231
    print(f"  Validation set:   {len(valid_data)} ({(1 - TRAIN_SPLIT) * 100:.0f}%)")  # noqa: E231
    print()

    # Show distribution by property
    from collections import Counter

    properties = Counter()
    for pair in qa_data:
        prop = pair.get("property", "Unknown")
        properties[prop] += 1

    print("  Distribution by property:")
    for prop, count in properties.most_common():
        print(f"    {prop}: {count}")

    print()
    print(f"  Output directory: {OUTPUT_DIR}")
    print()

    # Show a sample
    if formatted:
        sample = formatted[0]
        print("  Sample entry:")
        print(f"    System: {sample['messages'][0]['content'][:80]}...")
        print(f"    User:   {sample['messages'][1]['content'][:80]}")
        print(f"    Asst:   {sample['messages'][2]['content'][:80]}...")
    print()
    print("Done. Next step: python scripts/finetune_mlx.py")


if __name__ == "__main__":
    main()
