"""Tests for the LangChain RAG implementation."""

import tempfile
import shutil
from pathlib import Path
import pytest

from app.rag.langchain_rag import LangChainRAG


@pytest.fixture
def tmp_dir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def lc_rag(tmp_dir):
    return LangChainRAG(
        persist_dir=str(Path(tmp_dir) / "lc_store"),
        collection="test_lc",
        chunk_size=200,
        chunk_overlap=20,
    )


class TestLangChainRAGIngest:
    def test_ingest_texts_returns_count(self, lc_rag):
        count = lc_rag.ingest_texts(
            ["Vampire Manor has gothic towers.", "Werewolf Lodge has a pool."],
            source="test",
        )
        assert count >= 2  # at least one chunk per text

    def test_ingest_folder_nonexistent(self, lc_rag):
        count = lc_rag.ingest_folder("/nonexistent/path")
        assert count == 0


class TestLangChainRAGSearch:
    def test_search_returns_results(self, lc_rag):
        lc_rag.ingest_texts(
            [
                "Vampire Manor offers eternal night ambiance "
                "with gothic towers.",
                "Werewolf Lodge has heated outdoor pool and moonlight yoga.",
                "Castle Frankenstein provides 24-hour room service.",
            ]
        )
        results = lc_rag.search("vampire gothic towers", k=2)
        assert "results" in results
        assert len(results["results"]) <= 2
        assert results["results"][0]["text"]  # has content
        assert "score" in results["results"][0]

    def test_search_format_matches_custom_rag(self, lc_rag):
        lc_rag.ingest_texts(["Test document about resorts."])
        results = lc_rag.search("resorts", k=1)

        assert "ok" in results
        assert "query" in results
        assert "results" in results
        assert isinstance(results["results"], list)
        if results["results"]:
            r = results["results"][0]
            assert "text" in r
            assert "meta" in r
            assert "score" in r
