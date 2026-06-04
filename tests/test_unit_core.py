from app.config import Settings
from app.core.tools import make_registry
from app.core.memory import MemoryStore
from app.rag.vector_rag import VectorRAG
from app.database.db import DatabaseManager


def test_settings_load():
    """Test that settings load correctly."""
    s = Settings()
    assert s.app_name
    assert s.database_url
    assert s.rag_collection


def test_settings_accept_mrc_prefix_aliases(monkeypatch):
    """Docker Compose still uses the legacy MRC_ prefix."""
    monkeypatch.delenv("RC_DATABASE_URL", raising=False)
    monkeypatch.delenv("RC_API_KEY", raising=False)
    monkeypatch.setenv("MRC_DATABASE_URL", "sqlite:///./mrc_alias.db")
    monkeypatch.setenv("MRC_API_KEY", "legacy-api-key")

    s = Settings()

    assert s.database_url == "sqlite:///./mrc_alias.db"
    assert s.api_key == "legacy-api-key"


def test_tool_registry():
    """Test tool registry initialization and basic operations."""
    db = DatabaseManager(Settings())
    rag = VectorRAG("./.rag_store", "test_collection")

    reg = make_registry(
        db=db,
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
