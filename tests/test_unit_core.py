from app.config import Settings
from app.core.tools import make_registry
from app.core.memory import MemoryStore
from app.services.pdf_generator import PDFGenerator
from app.rag.vector_rag import VectorRAG
from app.database.db import DatabaseManager


def test_settings_load():
    """Test that settings load correctly."""
    s = Settings()
    assert s.app_name
    assert s.database_url
    assert s.rag_collection


def test_tool_registry():
    """Test tool registry initialization and basic operations."""
    db = DatabaseManager(Settings())
    pdf = PDFGenerator("./test_pdfs")
    rag = VectorRAG("./.rag_store", "test_collection")

    reg = make_registry(
        db=db, pdf=pdf,
        rag_search_fn=lambda q, k=5: rag.search(q, k)
    )
    tools = reg.list()

    assert len(tools) > 0
    assert reg.get(tools[0].name)


def test_memory_store():
    """Test memory store initialization."""
    db = DatabaseManager(Settings())
    mem = MemoryStore(db=db)
    assert mem is not None


def test_vector_rag_initialization():
    """Test VectorRAG initializes correctly with HuggingFace embeddings."""
    rag = VectorRAG("./.rag_store_test", "test_collection")
    assert rag is not None
    assert rag.collection_name == "test_collection"
    assert rag.embedding_model == "all-MiniLM-L6-v2"  # Default model
