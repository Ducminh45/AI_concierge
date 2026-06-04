"""
Synthetic Dataset Generator for Monster Resort Concierge
=========================================================

Generates high-quality synthetic Q&A pairs for fine-tuning using GPT-4o.
Creates 100-200 examples covering all properties and use cases.

Usage:
    python generate_synthetic_dataset.py --output data/concierge_qa.json --num-samples 150
"""

import os
import json
import argparse
from typing import List, Dict
from openai import OpenAI
from pathlib import Path
from tqdm import tqdm
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Monster Resort properties and their key features
PROPERTIES = {
    "The Mummy Resort & Tomb-Service": {
        "rating": "4/5 Scarabs",
        "features": [
            "Sarcophagus Suites",
            "24-karat gold lining",
            "Afterlife Bistro",
            "honey-cakes",
            "eternal wine",
        ],
        "amenities": ["Snake Charming", "Afterlife Wake-Up Calls", "Internal Wi-Fi"],
        "location": "Giza plateau",
        "check_in": "Sunset",
        "check_out": "Before reincarnation",
    },
    "The Werewolf Lodge: Moon & Moor": {
        "rating": "5/5 Full Moons",
        "features": [
            "Deep-fur conditioning",
            "claw filing",
            "fang whitening",
            "Primal Buffet",
        ],
        "amenities": [
            "Moon Deck",
            "Heated Floors",
            "Mud Baths",
            "Soundproofing during full moon",
        ],
        "location": "Black Forest",
        "check_in": "Dusk",
        "check_out": "Dawn",
    },
    "Castle Frankenstein: High Voltage Luxury": {
        "rating": "4/5 Lightning Bolts",
        "features": [
            "Galvanic charging stations",
            "adjustable neck bolts",
            "Lightning Spa",
        ],
        "amenities": [
            "Village Torch & Pitchfork lounge",
            "Dr. Victor's clinic",
            "Brain Bar",
        ],
        "location": "Mountain castle",
        "check_in": "Stormy weather preferred",
        "powered_by": "Renewable lightning strikes",
    },
    "Vampire Manor: Eternal Night Inn": {
        "rating": "5/5 Moon Drops",
        "features": [
            "Coffin Suites",
            "blackout curtains",
            "Elixir mini-fridges",
            "hand-carved mahogany",
        ],
        "amenities": ["Bat Valet", "Elixir Bar", "No-Sun Deck", "garlic-free cuisine"],
        "location": "Gothic manor",
        "check_in": "After Sunset",
        "check_out": "Before Dawn",
    },
    "Zombie Bed & Breakfast: Bites & Beds": {
        "rating": "3/5 Brains",
        "features": [
            "Shamble Suites",
            "dirt-lined mattresses",
            "all-you-can-eat brains buffet",
        ],
        "amenities": [
            "Graveyard View",
            "Limb Locker",
            "Moan-Proof Walls",
            "limb loss support therapy",
        ],
        "location": "Suburban graveyard",
        "check_in": "Whenever",
        "check_out": "Never",
    },
    "Ghostly B&B: Spectral Stay": {
        "rating": "4/5 Ectoplasm",
        "features": [
            "Floating beds",
            "poltergeist pillow service",
            "invisible breakfast",
        ],
        "amenities": [
            "Phase Walls",
            "Cold Spot Spa",
            "Ouija Concierge",
            "Boo bootcamp",
        ],
        "location": "Haunted building",
        "check_in": "Anytime",
        "check_out": "Eternity (optional)",
    },
}


# Question templates for different categories
QUESTION_TEMPLATES = {
    "amenities": [
        "What spa services are available at {property}?",
        "What amenities does {property} offer?",
        "Tell me about the facilities at {property}",
        "What activities can I do at {property}?",
        "Does {property} have a {amenity}?",
    ],
    "rooms": [
        "What room types are available at {property}?",
        "Describe the rooms at {property}",
        "What are the suites like at {property}?",
        "Tell me about the accommodations at {property}",
    ],
    "policy": [
        "What time is check-in at {property}?",
        "When can I check out from {property}?",
        "What are the house rules at {property}?",
        "What is the cancellation policy at {property}?",
    ],
    "dining": [
        "What dining options are available at {property}?",
        "Tell me about the food at {property}",
        "Does {property} serve breakfast?",
        "What's on the menu at {property}?",
    ],
    "location": [
        "Where is {property} located?",
        "How do I get to {property}?",
        "What's near {property}?",
    ],
    "comparison": [
        "What's the difference between {property1} and {property2}?",
        "Which is better for families: {property1} or {property2}?",
        "Compare {property1} and {property2}",
    ],
    "booking": [
        "How do I book a room at {property}?",
        "I want to reserve {room_type} at {property}",
        "Book me a room at {property} for {date}",
        "Can I make a reservation at {property}?",
    ],
    "rating": [
        "What is {property}'s rating?",
        "How is {property} rated?",
        "What do guests think of {property}?",
    ],
    "general": [
        "Tell me about {property}",
        "What makes {property} special?",
        "Why should I stay at {property}?",
        "Give me an overview of {property}",
    ],
}


def create_prompt_for_qa_generation(
    property_name: str, property_data: dict, question: str
) -> str:
    """Create a prompt for GPT-4o to generate a concierge-style answer."""

    context = f"""You are the Monster Resort Concierge, an elegant and sophisticated guide.

Property: {property_name}
Rating: {property_data.get('rating', 'N/A')}
Features: {', '.join(property_data.get('features', []))}
Amenities: {', '.join(property_data.get('amenities', []))}
Location: {property_data.get('location', 'N/A')}
Check-in: {property_data.get('check_in', 'N/A')}
Check-out: {property_data.get('check_out', 'N/A')}

Question: {question}

Write a concise, elegant, gothic-themed answer (2-4 sentences max). Use vivid language like "velvet," "moonlight," "shadows," "candlelight." Be helpful but maintain the spooky atmosphere."""

    return context


def generate_qa_pair(
    client: OpenAI,
    property_name: str,
    property_data: dict,
    question: str,
    max_retries: int = 3,
) -> Dict:
    """Generate a single Q&A pair using GPT-4o."""

    prompt = create_prompt_for_qa_generation(property_name, property_data, question)

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are the Monster Resort Concierge. Answer questions elegantly with gothic flair.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.8,
                max_tokens=200,
                timeout=30.0,  # Add timeout
            )

            answer = response.choices[0].message.content.strip()

            return {
                "instruction": question,
                "input": "",  # LoRA format uses instruction + input
                "output": answer,
                "property": property_name,
                "category": "qa",
            }

        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 2**attempt  # Exponential backoff
                print(f"Retry {attempt + 1}/{max_retries} after error: {e}")
                import time

                time.sleep(wait_time)
            else:
                print(f"Error generating Q&A after {max_retries} attempts: {e}")
                return None


def generate_dataset(
    num_samples: int = 150, output_path: str = "data/concierge_qa.json"
) -> List[Dict]:
    """Generate full synthetic dataset."""

    # Initialize OpenAI
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("MRC_OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "OpenAI API key not found. Set OPENAI_API_KEY or MRC_OPENAI_API_KEY"
        )

    client = OpenAI(api_key=api_key)
    dataset = []

    print(f"🧙 Generating {num_samples} synthetic Q&A pairs...")
    print(f"📍 Properties: {len(PROPERTIES)}")
    print(f"📋 Question templates: {sum(len(v) for v in QUESTION_TEMPLATES.values())}")

    # Calculate distribution
    samples_per_property = num_samples // len(PROPERTIES)

    with tqdm(total=num_samples, desc="Generating dataset") as pbar:
        for property_name, property_data in PROPERTIES.items():
            property_samples = 0

            # Generate samples for this property
            for category, templates in QUESTION_TEMPLATES.items():
                if property_samples >= samples_per_property:
                    break

                for template in templates:
                    if property_samples >= samples_per_property:
                        break

                    # Format question based on category
                    import random

                    if category == "comparison":
                        # Pick another property for comparison
                        other_properties = [
                            p for p in PROPERTIES.keys() if p != property_name
                        ]
                        other_prop = random.choice(other_properties)
                        question = template.format(
                            property1=property_name, property2=other_prop
                        )
                    elif "{amenity}" in template:
                        amenity = property_data.get("amenities", ["spa"])[0]
                        question = template.format(
                            property=property_name, amenity=amenity
                        )
                    elif "{room_type}" in template and "{date}" in template:
                        room_type = property_data.get("features", ["room"])[0]
                        question = template.format(
                            property=property_name, room_type=room_type, date="tonight"
                        )
                    elif "{room_type}" in template:
                        room_type = property_data.get("features", ["room"])[0]
                        question = template.format(
                            property=property_name, room_type=room_type
                        )
                    elif "{date}" in template:
                        question = template.format(
                            property=property_name, date="tonight"
                        )
                    else:
                        question = template.format(property=property_name)

                    # Generate Q&A pair
                    qa_pair = generate_qa_pair(
                        client, property_name, property_data, question
                    )

                    if qa_pair:
                        dataset.append(qa_pair)
                        property_samples += 1
                        pbar.update(1)
                        import time

                        time.sleep(0.5)  # Small delay to avoid rate limits

    # Add some cross-property questions
    print("\n🌐 Adding cross-property questions...")
    cross_property_questions = [
        "What time is check-in across all properties?",
        "Which properties are best for nocturnal guests?",
        "Compare all the spa services available",
        "What are the dining options across the resort?",
        "Which property has the best rating?",
    ]

    for question in cross_property_questions:
        # Generate answer using all property data
        context = "Monster Resort Properties Overview:\n\n"
        for prop_name, prop_data in PROPERTIES.items():
            context += f"{prop_name}: {prop_data.get('rating', 'N/A')}, {', '.join(prop_data.get('features', [])[:3])}\n"

        prompt = f"{context}\nQuestion: {question}\n\nProvide a concise, gothic-themed answer:"

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are the Monster Resort Concierge.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.8,
                max_tokens=250,
            )

            dataset.append(
                {
                    "instruction": question,
                    "input": "",
                    "output": response.choices[0].message.content.strip(),
                    "property": "All",
                    "category": "cross_property",
                }
            )
        except Exception as e:
            print(f"Error with cross-property question: {e}")

    # Save dataset
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Dataset saved to {output_path}")
    print(f"📊 Total samples: {len(dataset)}")
    print(f"📋 Distribution:")

    # Show distribution
    from collections import Counter

    property_counts = Counter(d["property"] for d in dataset)
    for prop, count in property_counts.most_common():
        print(f"   {prop}: {count} samples")

    return dataset


def validate_dataset(dataset_path: str):
    """Validate the generated dataset."""

    with open(dataset_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    print(f"\n🔍 Validating dataset: {dataset_path}")
    print(f"Total samples: {len(dataset)}")

    # Check format
    required_keys = ["instruction", "input", "output"]
    valid = all(all(k in sample for k in required_keys) for sample in dataset)

    if valid:
        print("✅ Format is correct (instruction, input, output)")
    else:
        print("❌ Format error: Missing required keys")
        return False

    # Check for empty outputs
    empty_outputs = sum(1 for d in dataset if not d["output"].strip())
    if empty_outputs > 0:
        print(f"⚠️  Warning: {empty_outputs} samples have empty outputs")

    # Check output lengths
    avg_output_len = sum(len(d["output"]) for d in dataset) / len(dataset)
    print(f"📏 Average output length: {avg_output_len:.0f} characters")

    # Show sample
    print("\n📋 Sample Q&A:")
    import random

    sample = random.choice(dataset)
    print(f"Q: {sample['instruction']}")
    print(f"A: {sample['output']}")

    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate synthetic Monster Resort Q&A dataset"
    )
    parser.add_argument(
        "--output", type=str, default="data/concierge_qa.json", help="Output file path"
    )
    parser.add_argument(
        "--num-samples", type=int, default=150, help="Number of samples to generate"
    )
    parser.add_argument("--validate", type=str, help="Validate existing dataset")

    args = parser.parse_args()

    if args.validate:
        validate_dataset(args.validate)
    else:
        dataset = generate_dataset(
            num_samples=args.num_samples, output_path=args.output
        )
        validate_dataset(args.output)
