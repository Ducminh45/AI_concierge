from langchain_huggingface import HuggingFaceEmbeddings
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy
from datasets import Dataset


# Initialize a lightweight, stable local embedding model
hf_embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)


def evaluate_rag_batch(samples):
    dataset = Dataset.from_list(samples)

    # We tell RAGAS to use our local HF embeddings instead of OpenAI
    results = evaluate(
        dataset, metrics=[faithfulness, answer_relevancy], embeddings=hf_embeddings
    )

    return results.to_pandas().to_dict()
