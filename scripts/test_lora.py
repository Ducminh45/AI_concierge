"""
Test LoRA Fine-tuned Model
===========================

Quick script to test your fine-tuned LoRA model on Monster Resort queries.

Usage:
    python test_lora.py --adapter lora-concierge/final --query "What spa services are available?"
    python test_lora.py --adapter lora-concierge/final --interactive
"""

import argparse
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel


def load_lora_model(
    adapter_path: str, base_model: str = "microsoft/Phi-3-mini-4k-instruct"
):
    """Load base model with LoRA adapter."""

    print(f"📥 Loading base model: {base_model}")

    # Load tokenizer
    tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)
    tokenizer.pad_token = tokenizer.eos_token

    # Load base model
    model = AutoModelForCausalLM.from_pretrained(
        base_model, torch_dtype=torch.float16, device_map="auto", trust_remote_code=True
    )

    # Load LoRA adapter
    print(f"🔧 Loading LoRA adapter: {adapter_path}")
    model = PeftModel.from_pretrained(model, adapter_path)
    model.eval()

    print("✅ Model loaded successfully!")
    return model, tokenizer


def generate_response(
    model,
    tokenizer,
    query: str,
    max_new_tokens: int = 200,
    temperature: float = 0.7,
    top_p: float = 0.9,
) -> str:
    """Generate response to query using fine-tuned model."""

    # Format as Phi-3 chat
    prompt = f"<|user|>\n{query}<|end|>\n<|assistant|>\n"

    # Tokenize
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

    # Generate
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            top_p=top_p,
            do_sample=True,
            pad_token_id=tokenizer.eos_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )

    # Decode
    full_response = tokenizer.decode(outputs[0], skip_special_tokens=True)

    # Extract just the assistant's response
    if "<|assistant|>" in full_response:
        response = full_response.split("<|assistant|>")[-1].strip()
    else:
        response = full_response.replace(prompt, "").strip()

    return response


def interactive_mode(model, tokenizer):
    """Interactive testing mode."""

    print("\n🧛 Monster Resort Concierge (LoRA Model)")
    print("=" * 60)
    print("Type your questions or 'quit' to exit\n")

    test_queries = [
        "What spa services are available at Castle Frankenstein?",
        "Tell me about Vampire Manor",
        "What room types does Zombie Bed & Breakfast have?",
        "Which properties are best for nocturnal guests?",
        "What time is check-in?",
    ]

    print("💡 Example queries:")
    for i, q in enumerate(test_queries, 1):
        print(f"   {i}. {q}")
    print()

    while True:
        query = input("🧙 You: ").strip()

        if query.lower() in ["quit", "exit", "q"]:
            print("\n👋 Farewell, mortal!")
            break

        if not query:
            continue

        # Handle numbered shortcuts
        if query.isdigit() and 1 <= int(query) <= len(test_queries):
            query = test_queries[int(query) - 1]
            print(f"   Using: {query}")

        print("\n🕯️  Generating response...")
        response = generate_response(model, tokenizer, query)
        print(f"\n🧛 Concierge: {response}\n")


def batch_test(model, tokenizer, adapter_path: str):
    """Run batch test on common queries."""

    test_cases = [
        {
            "query": "What spa services are available at Castle Frankenstein?",
            "category": "amenities",
        },
        {
            "query": "Tell me about Vampire Manor: Eternal Night Inn",
            "category": "property_overview",
        },
        {
            "query": "What room types are available at Zombie Bed & Breakfast?",
            "category": "rooms",
        },
        {"query": "What time is check-in?", "category": "policy"},
        {
            "query": "Which properties are best for nocturnal guests?",
            "category": "recommendation",
        },
        {"query": "Compare Vampire Manor and Werewolf Lodge", "category": "comparison"},
    ]

    print("\n🧪 Running Batch Test")
    print("=" * 70)

    results = []

    for i, test_case in enumerate(test_cases, 1):
        query = test_case["query"]
        category = test_case["category"]

        print(f"\n[{i}/{len(test_cases)}] {category.upper()}")
        print(f"Q: {query}")

        response = generate_response(model, tokenizer, query)

        print(f"A: {response}")
        print("-" * 70)

        results.append({"query": query, "response": response, "category": category})

    # Save results
    import json
    from pathlib import Path

    output_path = Path(adapter_path).parent / "test_results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Test complete! Results saved to {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test LoRA fine-tuned model")

    parser.add_argument(
        "--adapter", type=str, required=True, help="Path to LoRA adapter"
    )
    parser.add_argument(
        "--base-model",
        type=str,
        default="microsoft/Phi-3-mini-4k-instruct",
        help="Base model",
    )
    parser.add_argument("--query", type=str, help="Single query to test")
    parser.add_argument("--interactive", action="store_true", help="Interactive mode")
    parser.add_argument("--batch", action="store_true", help="Run batch test")
    parser.add_argument(
        "--max-tokens", type=int, default=200, help="Max tokens to generate"
    )
    parser.add_argument(
        "--temperature", type=float, default=0.7, help="Sampling temperature"
    )

    args = parser.parse_args()

    # Load model
    model, tokenizer = load_lora_model(args.adapter, args.base_model)

    # Run appropriate mode
    if args.interactive:
        interactive_mode(model, tokenizer)
    elif args.batch:
        batch_test(model, tokenizer, args.adapter)
    elif args.query:
        print(f"\nQuery: {args.query}")
        response = generate_response(
            model,
            tokenizer,
            args.query,
            max_new_tokens=args.max_tokens,
            temperature=args.temperature,
        )
        print(f"\nResponse: {response}")
    else:
        print("❌ Please specify --query, --interactive, or --batch")
        print("\nExamples:")
        print(
            '  python test_lora.py --adapter lora-concierge/final --query "Tell me about Vampire Manor"'
        )
        print("  python test_lora.py --adapter lora-concierge/final --interactive")
        print("  python test_lora.py --adapter lora-concierge/final --batch")
