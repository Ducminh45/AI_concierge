"""MLX LoRA fine-tuning wrapper for TinyLlama on Apple Silicon."""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TRAIN_DATA = PROJECT_ROOT / "data" / "finetune" / "train.jsonl"
VALID_DATA = PROJECT_ROOT / "data" / "finetune" / "valid.jsonl"
ADAPTER_DIR = PROJECT_ROOT / "lora-adapters"

# Model configuration
MODEL_NAME = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"

# LoRA hyperparameters
NUM_ITERS = 600
BATCH_SIZE = 4
NUM_LORA_LAYERS = 8
LEARNING_RATE = 1e-5
LORA_RANK = 8
STEPS_PER_EVAL = 100
STEPS_PER_REPORT = 10
SAVE_EVERY = 200


def check_platform():
    """Verify we are on Apple Silicon."""
    import platform

    if platform.system() != "Darwin":
        print("ERROR: This script requires macOS with Apple Silicon (M1/M2/M3/M4).")
        print("       MLX only runs on Apple Silicon Macs.")
        sys.exit(1)

    machine = platform.machine()
    if machine != "arm64":
        print(f"WARNING: Detected architecture '{machine}'. MLX requires Apple Silicon (arm64).")
        print("         This may not work on Intel Macs.")


def check_dependencies():
    """Check that mlx-lm is installed."""
    try:
        import mlx_lm  # noqa: F401

        print("  mlx-lm is installed")
    except ImportError:
        print("ERROR: mlx-lm is not installed.")
        print()
        print("Install it with:")
        print("  pip install mlx-lm")
        print()
        print("Or with uv:")
        print("  uv pip install mlx-lm")
        sys.exit(1)

    try:
        import mlx.core  # noqa: F401

        print("  mlx is installed")
    except ImportError:
        print("ERROR: mlx is not installed (should come with mlx-lm).")
        print("  pip install mlx")
        sys.exit(1)


def check_training_data():
    """Verify training data exists."""
    if not TRAIN_DATA.exists():
        print(f"ERROR: Training data not found at {TRAIN_DATA}")
        print()
        print("Generate it first:")
        print("  python scripts/prep_finetune_data.py")
        sys.exit(1)

    if not VALID_DATA.exists():
        print(f"ERROR: Validation data not found at {VALID_DATA}")
        print()
        print("Generate it first:")
        print("  python scripts/prep_finetune_data.py")
        sys.exit(1)

    # Count lines
    with open(TRAIN_DATA) as f:
        train_count = sum(1 for _ in f)
    with open(VALID_DATA) as f:
        valid_count = sum(1 for _ in f)

    print(f"  Training samples:   {train_count}")
    print(f"  Validation samples: {valid_count}")

    if train_count < 10:
        print("WARNING: Very few training samples. Results may be poor.")


def run_finetuning():
    """Run mlx_lm.lora with configured hyperparameters."""
    ADAPTER_DIR.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, "-m", "mlx_lm.lora",
        "--model", MODEL_NAME,
        "--train",
        "--data", str(PROJECT_ROOT / "data" / "finetune"),
        "--adapter-path", str(ADAPTER_DIR),
        "--iters", str(NUM_ITERS),
        "--batch-size", str(BATCH_SIZE),
        "--num-layers", str(NUM_LORA_LAYERS),
        "--learning-rate", str(LEARNING_RATE),
        "--lora-rank", str(LORA_RANK),
        "--steps-per-eval", str(STEPS_PER_EVAL),
        "--steps-per-report", str(STEPS_PER_REPORT),
        "--save-every", str(SAVE_EVERY),
    ]

    print()
    print("Running command:")
    print(f"  {' '.join(cmd)}")
    print()
    print("-" * 60)

    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))

    if result.returncode != 0:
        print()
        print(f"ERROR: Fine-tuning exited with code {result.returncode}")
        sys.exit(1)

    print("-" * 60)
    print()
    print(f"Adapter weights saved to: {ADAPTER_DIR}")


def test_with_sample_prompt():
    """Generate a sample response using the fine-tuned adapter."""
    print()
    print("=" * 60)
    print("  Testing with a sample prompt")
    print("=" * 60)
    print()

    test_prompt = "What spa services are available at the Mummy Resort?"

    cmd = [
        sys.executable, "-m", "mlx_lm.generate",
        "--model", MODEL_NAME,
        "--adapter-path", str(ADAPTER_DIR),
        "--prompt", test_prompt,
        "--max-tokens", "200",
    ]

    print(f"Prompt: {test_prompt}")
    print()
    print("Response:")
    print("-" * 40)

    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True)

    if result.returncode == 0:
        # mlx_lm.generate prints to stdout
        output = result.stdout.strip()
        if output:
            print(output)
        else:
            print("(no output captured -- check console above)")
    else:
        print(f"WARNING: Generate command failed (exit code {result.returncode})")
        if result.stderr:
            print(f"  stderr: {result.stderr[:300]}")

    print("-" * 40)


def main():
    print("=" * 60)
    print("  Monster Resort -- MLX LoRA Fine-Tuning")
    print("=" * 60)
    print()

    # Pre-flight checks
    print("Pre-flight checks:")
    check_platform()
    check_dependencies()
    check_training_data()
    print()
    print("All checks passed.")

    # Show configuration
    print()
    print("Configuration:")
    print(f"  Model:           {MODEL_NAME}")
    print(f"  Iterations:      {NUM_ITERS}")
    print(f"  Batch size:      {BATCH_SIZE}")
    print(f"  LoRA layers:     {NUM_LORA_LAYERS}")
    print(f"  LoRA rank:       {LORA_RANK}")
    print(f"  Learning rate:   {LEARNING_RATE}")
    print(f"  Eval every:      {STEPS_PER_EVAL} steps")
    print(f"  Save every:      {SAVE_EVERY} steps")
    print(f"  Adapter output:  {ADAPTER_DIR}")
    print()

    # Run fine-tuning
    print("Starting fine-tuning...")
    print("(This takes ~20-30 minutes on M1 Pro, ~10-15 on M3 Max)")
    print()
    run_finetuning()

    # Test
    test_with_sample_prompt()

    # Summary
    print()
    print("=" * 60)
    print("  Fine-tuning complete!")
    print("=" * 60)
    print()
    print(f"  Adapter weights: {ADAPTER_DIR}")
    print()
    print("  Next steps:")
    print("    1. Test more prompts:")
    print(f"       python -m mlx_lm.generate --model {MODEL_NAME} \\")
    print(f"         --adapter-path {ADAPTER_DIR} \\")  # noqa: E221
    print('         --prompt "Tell me about Vampire Manor"')
    print()
    print("    2. Compare RAG vs fine-tuned:")
    print("       python scripts/compare_rag_vs_finetune.py")
    print()


if __name__ == "__main__":
    main()
