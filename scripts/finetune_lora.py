"""LoRA fine-tuning script for Phi-3-mini on the Monster Resort Q&A dataset."""

import argparse
import json
import torch
from pathlib import Path
from datetime import datetime
from typing import Dict, List

from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
    Trainer,
    DataCollatorForLanguageModeling,
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from datasets import Dataset, load_dataset


def format_instruction(sample: Dict) -> str:
    """
    Format sample into Phi-3 instruction format.

    Phi-3 format:
    <|user|>
    Question here<|end|>
    <|assistant|>
    Answer here<|end|>
    """
    instruction = sample.get("instruction", "")
    input_text = sample.get("input", "")
    output = sample.get("output", "")

    # Combine instruction and input if input exists
    if input_text:
        user_message = f"{instruction}\n{input_text}"
    else:
        user_message = instruction

    # Phi-3 chat template
    formatted = f"<|user|>\n{user_message}<|end|>\n" f"<|assistant|>\n{output}<|end|>"

    return formatted


def load_and_prepare_dataset(dataset_path: str, tokenizer, max_length: int = 512):
    """Load and tokenize the dataset."""

    print(f"📂 Loading dataset from {dataset_path}")

    # Load JSON dataset
    with open(dataset_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"✅ Loaded {len(data)} samples")

    # Format samples
    formatted_samples = []
    for sample in data:
        formatted_text = format_instruction(sample)
        formatted_samples.append({"text": formatted_text})

    # Create HuggingFace dataset
    dataset = Dataset.from_list(formatted_samples)

    # Split into train/eval (90/10)
    dataset = dataset.train_test_split(test_size=0.1, seed=42)

    print(f"📊 Train samples: {len(dataset['train'])}")
    print(f"📊 Eval samples: {len(dataset['test'])}")

    # Tokenize
    def tokenize_function(examples):
        outputs = tokenizer(
            examples["text"],
            truncation=True,
            max_length=max_length,
            padding="max_length",
            return_tensors="pt",
        )
        outputs["labels"] = outputs["input_ids"].clone()
        return outputs

    print("🔄 Tokenizing dataset...")
    tokenized_dataset = dataset.map(
        tokenize_function,
        batched=True,
        remove_columns=dataset["train"].column_names,
        desc="Tokenizing",
    )

    return tokenized_dataset


def create_lora_config(
    r: int = 16,
    lora_alpha: int = 32,
    lora_dropout: float = 0.05,
    target_modules: List[str] = None,
) -> LoraConfig:
    """
    Create LoRA configuration.

    Args:
        r: LoRA rank (higher = more parameters, better quality, slower)
        lora_alpha: LoRA alpha (scaling factor)
        lora_dropout: Dropout probability
        target_modules: Which modules to apply LoRA to
    """

    if target_modules is None:
        # Phi-3 attention modules
        target_modules = ["q_proj", "k_proj", "v_proj", "o_proj"]

    config = LoraConfig(
        r=r,
        lora_alpha=lora_alpha,
        target_modules=target_modules,
        lora_dropout=lora_dropout,
        bias="none",
        task_type="CAUSAL_LM",
    )

    print("⚙️  LoRA Configuration:")
    print(f"   Rank (r): {r}")
    print(f"   Alpha: {lora_alpha}")
    print(f"   Dropout: {lora_dropout}")
    print(f"   Target modules: {target_modules}")

    return config


def finetune_lora(
    dataset_path: str,
    output_dir: str = "lora-concierge",
    model_name: str = "microsoft/Phi-3-mini-4k-instruct",
    epochs: int = 3,
    batch_size: int = 4,
    gradient_accumulation_steps: int = 4,
    learning_rate: float = 2e-4,
    max_length: int = 512,
    use_gpu: bool = False,
    lora_r: int = 16,
    lora_alpha: int = 32,
):
    """Main fine-tuning function."""

    print("🚀 Starting LoRA Fine-tuning for Monster Resort Concierge")
    print("=" * 70)

    # Device setup
    device = "cuda" if use_gpu and torch.cuda.is_available() else "cpu"
    print(f"🖥️  Device: {device}")

    if device == "cpu":
        print("⚠️  WARNING: Training on CPU will be slow (8-12 hours)")
        print("   Consider using Google Colab with free T4 GPU")

    # Load tokenizer
    print(f"\n📥 Loading tokenizer: {model_name}")
    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    # Load model
    print(f"📥 Loading model: {model_name}")
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        torch_dtype=torch.float16 if device == "cuda" else torch.float32,
        device_map="auto" if device == "cuda" else None,
        trust_remote_code=True,
    )

    if device == "cpu":
        model = model.to("cpu")

    # Prepare model for LoRA
    print("\n🔧 Preparing model for LoRA training...")
    if device == "cuda":
        model = prepare_model_for_kbit_training(model)

    # Apply LoRA
    lora_config = create_lora_config(r=lora_r, lora_alpha=lora_alpha)
    model = get_peft_model(model, lora_config)

    # Print trainable parameters
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total_params = sum(p.numel() for p in model.parameters())
    print(f"\n📊 Model Statistics:")
    print(
        f"   Trainable parameters: {trainable_params:,} ({100 * trainable_params / total_params:.2f}%)"
    )
    print(f"   Total parameters: {total_params:,}")

    # Load dataset
    tokenized_dataset = load_and_prepare_dataset(dataset_path, tokenizer, max_length)

    # Training arguments
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    training_args = TrainingArguments(
        output_dir=str(output_path),
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size,
        gradient_accumulation_steps=gradient_accumulation_steps,
        learning_rate=learning_rate,
        lr_scheduler_type="cosine",
        warmup_steps=100,
        logging_steps=10,
        save_steps=100,
        eval_steps=100,
        eval_strategy="steps",
        save_total_limit=2,
        load_best_model_at_end=True,
        report_to="none",
        fp16=device == "cuda",
        optim="adamw_torch",
        seed=42,
        dataloader_pin_memory=True if device == "cuda" else False,
    )

    print("\n📋 Training Configuration:")
    print(f"   Epochs: {epochs}")
    print(f"   Batch size: {batch_size}")
    print(f"   Gradient accumulation: {gradient_accumulation_steps}")
    print(f"   Effective batch size: {batch_size * gradient_accumulation_steps}")
    print(f"   Learning rate: {learning_rate}")
    print(f"   Max length: {max_length}")
    print(f"   Output: {output_dir}")

    # Data collator
    data_collator = DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)

    # Trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_dataset["train"],
        eval_dataset=tokenized_dataset["test"],
        data_collator=data_collator,
    )

    # Train
    print("\n🎓 Starting training...")
    print(f"⏰ Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    if device == "cpu":
        print("\n💡 TIP: Press Ctrl+C to stop training early if needed")
        print("   You can resume later from the last checkpoint\n")

    trainer.train()

    print(f"\n✅ Training complete!")
    print(f"⏰ End time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Save final model
    final_path = output_path / "final"
    final_path.mkdir(exist_ok=True)

    print(f"\n💾 Saving final LoRA adapter to {final_path}")
    model.save_pretrained(final_path)
    tokenizer.save_pretrained(final_path)

    # Save training info
    info = {
        "model_name": model_name,
        "dataset_path": dataset_path,
        "train_samples": len(tokenized_dataset["train"]),
        "eval_samples": len(tokenized_dataset["test"]),
        "epochs": epochs,
        "lora_r": lora_r,
        "lora_alpha": lora_alpha,
        "learning_rate": learning_rate,
        "device": device,
        "training_date": datetime.now().isoformat(),
    }

    with open(final_path / "training_info.json", "w") as f:
        json.dump(info, f, indent=2)

    print("\n🎉 All done! Your LoRA adapter is ready.")
    print(f"📁 Adapter location: {final_path}")
    print("\nNext steps:")
    print("1. Test the model with test_lora.py")
    print("2. Integrate into your app with lora_integration.py")
    print("3. Run comparison evaluation with evaluate_lora.py")

    return str(final_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fine-tune Phi-3-mini with LoRA for Monster Resort"
    )

    parser.add_argument(
        "--dataset", type=str, required=True, help="Path to dataset JSON file"
    )
    parser.add_argument(
        "--output", type=str, default="lora-concierge", help="Output directory"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="microsoft/Phi-3-mini-4k-instruct",
        help="Base model",
    )
    parser.add_argument("--epochs", type=int, default=3, help="Number of epochs")
    parser.add_argument(
        "--batch-size", type=int, default=4, help="Batch size per device"
    )
    parser.add_argument(
        "--gradient-accumulation",
        type=int,
        default=4,
        help="Gradient accumulation steps",
    )
    parser.add_argument(
        "--learning-rate", type=float, default=2e-4, help="Learning rate"
    )
    parser.add_argument(
        "--max-length", type=int, default=512, help="Max sequence length"
    )
    parser.add_argument("--gpu", action="store_true", help="Use GPU if available")
    parser.add_argument("--lora-r", type=int, default=16, help="LoRA rank")
    parser.add_argument("--lora-alpha", type=int, default=32, help="LoRA alpha")

    args = parser.parse_args()

    # Check if dataset exists
    if not Path(args.dataset).exists():
        print(f"❌ Dataset not found: {args.dataset}")
        print("\nGenerate dataset first:")
        print("  python generate_synthetic_dataset.py --output data/concierge_qa.json")
        exit(1)

    # Run training
    finetune_lora(
        dataset_path=args.dataset,
        output_dir=args.output,
        model_name=args.model,
        epochs=args.epochs,
        batch_size=args.batch_size,
        gradient_accumulation_steps=args.gradient_accumulation,
        learning_rate=args.learning_rate,
        max_length=args.max_length,
        use_gpu=args.gpu,
        lora_r=args.lora_r,
        lora_alpha=args.lora_alpha,
    )
