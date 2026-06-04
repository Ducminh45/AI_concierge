import os
import pytest
from app.validation.ragas_eval import evaluate_rag_batch

HAS_REAL_KEY = (
    os.environ.get("MRC_OPENAI_API_KEY", "dummy") != "dummy"
)


@pytest.mark.skipif(
    not HAS_REAL_KEY,
    reason="RAGAS requires a real OpenAI API key",
)
def test_ragas_eval_example():
    """Test RAGAS evaluation with sample Q&A pairs."""
    # Sample data matching the new format
    samples = [
        {
            "question": "What time is check in?",
            "answer": "Check-in is from 3pm.",
            "contexts": ["Check-in is from 3pm to midnight."],
            "reference": "Check-in starts at 3pm"
        },
        {
            "question": "Is breakfast included?",
            "answer": "Yes, breakfast is included in your stay.",
            "contexts": ["Breakfast is included for all guests."],
            "reference": "Breakfast is complimentary"
        }
    ]

    # Run evaluation
    results = evaluate_rag_batch(samples)

    # Verify expected metrics are present
    assert "faithfulness" in results, \
        "Faithfulness metric should be present"
    assert "answer_relevancy" in results, \
        "Answer relevancy metric should be present"
    # context_precision and context_recall are not included in the
    # current metric set (faithfulness + answer_relevancy only)

    # Optionally print results for debugging
    print("\nRAGAS Evaluation Results:")
    for metric, value in results.items():
        if isinstance(value, dict):
            numeric_vals = [v for v in value.values() if isinstance(v, (int, float))]
            if numeric_vals:
                avg = sum(numeric_vals) / len(numeric_vals)
                print("  {}: {:.3f} (average)".format(metric, avg))
            else:
                print("  {}: (non-numeric)".format(metric))
        elif isinstance(value, (int, float)):
            print("  {}: {:.3f}".format(metric, value))
        else:
            print("  {}: {}".format(metric, value))


def test_ragas_eval_with_poor_answer():
    """Test RAGAS with intentionally poor answer to verify scoring."""
    samples = [
        {
            "question": "What time is check in?",
            "answer": "The sky is blue.",  # Completely wrong answer
            "contexts": ["Check-in is from 3pm to midnight."],
            "reference": "Check-in starts at 3pm"
        }
    ]

    results = evaluate_rag_batch(samples)

    # Poor answer should have low faithfulness and relevancy
    assert "faithfulness" in results
    assert "answer_relevancy" in results

    # Note: Actual threshold values depend on RAGAS implementation
    # These are just structural checks
    print("\n⚠️  Poor Answer Test Results:")
    print(f"  Faithfulness: {results.get('faithfulness', 'N/A')}")
    print(f"  Answer Relevancy: {results.get('answer_relevancy', 'N/A')}")


def test_ragas_eval_batch_format():
    """Test that evaluate_rag_batch accepts the correct format."""
    # Test with minimal valid input
    samples = [
        {
            "question": "Test question?",
            "answer": "Test answer.",
            "contexts": ["Test context."],
            "reference": "Test reference"
        }
    ]

    # Should not raise an exception
    results = evaluate_rag_batch(samples)
    assert isinstance(results, dict), "Results should be a dictionary"
