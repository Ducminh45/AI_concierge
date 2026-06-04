import os
import tempfile
import shutil
from pathlib import Path
import pytest
import sqlite3
from fastapi.testclient import TestClient
from app.main import build_app


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    """Setup test environment variables before each test."""
    # Set OpenAI API key from environment or use a test placeholder
    if not os.getenv("OPENAI_API_KEY") and not os.getenv("MRC_OPENAI_API_KEY"):
        # If no API key is set, use a placeholder for tests
        monkeypatch.setenv("OPENAI_API_KEY", "test-key-placeholder")

    # Disable tokenizers parallelism warning
    monkeypatch.setenv("TOKENIZERS_PARALLELISM", "false")
    monkeypatch.setenv("RC_API_KEY", "dummy")
    monkeypatch.setenv("MRC_API_KEY", "dummy")

    from app.config import get_settings
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def reset_db(client):
    """Reset database before each test for isolation."""
    db_url = os.environ.get("MRC_DATABASE_URL")
    if db_url and db_url.startswith("sqlite:///"):
        db_path = db_url.replace("sqlite:///", "", 1)
        if Path(db_path).exists():
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            tables = [
                "bookings", "messages", "sessions",
                "api_keys", "api_key_usage",
            ]
            for table in tables:
                try:
                    cursor.execute(f"DELETE FROM {table}")
                except Exception:
                    pass
            conn.commit()
            conn.close()


@pytest.fixture(scope="session")
def tmp_dir():
    """Create temporary directory for test files."""
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture()
def client(tmp_dir, monkeypatch):
    """Create test client with isolated database and RAG store."""
    # Override environment variables for test isolation
    db_path = str(Path(tmp_dir) / "test.db")
    rag_path = str(Path(tmp_dir) / ".rag_store")

    monkeypatch.setenv(
        "MRC_DATABASE_URL", "sqlite:///" + db_path
    )
    monkeypatch.setenv("MRC_RAG_PERSIST_DIR", rag_path)
    monkeypatch.setenv("MRC_ENABLE_GRADIO", "false")

    # Also set RC_ prefix equivalents for settings
    monkeypatch.setenv("RC_DATABASE_URL", "sqlite:///" + db_path)
    monkeypatch.setenv("RC_RAG_PERSIST_DIR", rag_path)
    monkeypatch.setenv("RC_ENABLE_GRADIO", "false")
    monkeypatch.setenv("RC_API_KEY", "dummy")
    monkeypatch.setenv("MRC_API_KEY", "dummy")

    from app.config import get_settings
    get_settings.cache_clear()

    # Ensure OpenAI API key is set (use from environment or placeholder)
    if not os.getenv("OPENAI_API_KEY"):
        monkeypatch.setenv("OPENAI_API_KEY", "test-key-placeholder")

    app = build_app()
    return TestClient(app, raise_server_exceptions=False)
