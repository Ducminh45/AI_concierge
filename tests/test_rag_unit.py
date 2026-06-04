from app.rag.vector_rag import VectorRAG


def test_rag_ingest_and_search(tmp_path):
    """Test RAG ingestion and search with HuggingFace embeddings."""
    # Create a test folder and file
    folder = tmp_path / "knowledge"
    folder.mkdir()
    file = folder / "test.txt"
    file.write_text(
        "The Mummy Resort is ancient and mysterious, "
        "located in the heart of the desert."
    )

    # Initialize VectorRAG with HuggingFace embeddings
    rag = VectorRAG(str(tmp_path / ".rag_store"), "test_collection")

    # Ingest the test file
    count = rag.ingest_folder(str(folder))
    assert count == 1, "Should have ingested 1 document"

    # Search for content
    result = rag.search("Mummy", k=1)
    assert result is not None
    assert result["ok"] is True
    assert len(result["results"]) > 0
    assert "Mummy" in result["results"][0]["text"]


def test_rag_multiple_documents(tmp_path):
    """Test RAG with multiple documents."""
    # Create test folder with multiple files
    folder = tmp_path / "knowledge"
    folder.mkdir()

    (folder / "vampires.txt").write_text(
        "Vampire Manor offers eternal luxury with coffin suites."
    )
    (folder / "zombies.txt").write_text(
        "Zombie Bed & Breakfast serves brains for breakfast."
    )
    (folder / "mummies.txt").write_text(
        "The Mummy Resort wraps you in ancient comfort."
    )

    # Initialize and ingest
    rag = VectorRAG(str(tmp_path / ".rag_store"), "multi_doc_test")
    count = rag.ingest_folder(str(folder))
    assert count == 3, "Should have ingested 3 documents"

    # Search for vampire content
    result = rag.search("vampire luxury", k=2)
    assert result["ok"] is True
    assert len(result["results"]) > 0

    # Verify vampire content is in results
    results_text = " ".join([r["text"] for r in result["results"]])
    assert "Vampire" in results_text or "vampire" in results_text.lower()


def test_rag_empty_folder(tmp_path):
    """Test RAG with empty folder."""
    folder = tmp_path / "empty_knowledge"
    folder.mkdir()

    rag = VectorRAG(str(tmp_path / ".rag_store"), "empty_test")
    count = rag.ingest_folder(str(folder))
    assert count == 0, "Should have ingested 0 documents from empty folder"


def test_rag_search_no_results(tmp_path):
    """Test RAG search when no matching results exist."""
    folder = tmp_path / "knowledge"
    folder.mkdir()
    (folder / "test.txt").write_text("The resort has a spa.")

    rag = VectorRAG(str(tmp_path / ".rag_store"), "no_match_test")
    rag.ingest_folder(str(folder))

    # Search for something completely unrelated
    result = rag.search("quantum physics equations", k=5)
    assert result["ok"] is True
    # Should still return results (semantic search may find loosely
    # related content) but they won't be very relevant
