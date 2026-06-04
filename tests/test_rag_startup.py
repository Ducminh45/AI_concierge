from __future__ import annotations

from types import SimpleNamespace

from app.main import _ensure_knowledge_ingested


class FakeCollection:
    def __init__(self, count: int):
        self._count = count

    def count(self):
        return self._count


class FakeRAG:
    def __init__(self, count: int):
        self.collection = FakeCollection(count)
        self.calls = []

    def ingest_folder(self, folder: str, token: str | None = None):
        self.calls.append((folder, token))
        return 12


def test_startup_ingests_knowledge_when_vector_store_is_empty():
    rag = FakeRAG(count=0)
    settings = SimpleNamespace(rag_ingestion_token="token-123")

    count = _ensure_knowledge_ingested(
        rag,
        settings,
        knowledge_folder="/tmp/knowledge",
    )

    assert count == 12
    assert rag.calls == [("/tmp/knowledge", "token-123")]


def test_startup_skips_ingest_when_vector_store_has_documents():
    rag = FakeRAG(count=5)
    settings = SimpleNamespace(rag_ingestion_token="token-123")

    count = _ensure_knowledge_ingested(
        rag,
        settings,
        knowledge_folder="/tmp/knowledge",
    )

    assert count == 0
    assert rag.calls == []
