"""
LangChain RAG Implementation
=============================

A LangChain-based RAG implementation for benchmarking against the custom
AdvancedRAG. Uses the same interface (ingest_texts, ingest_folder, search)
so results are directly comparable.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import List

from ..monitoring.logging_utils import logger


class LangChainRAG:
    """LangChain-based RAG using Chroma and HuggingFace embeddings."""

    def __init__(
        self,
        persist_dir: str,
        collection: str,
        embedding_model: str = "all-MiniLM-L6-v2",
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ):
        from langchain_huggingface import HuggingFaceEmbeddings
        from langchain_community.vectorstores import Chroma

        self.persist_dir = persist_dir
        self.collection_name = collection
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        self._embeddings = HuggingFaceEmbeddings(model_name=embedding_model)
        self._vectorstore = Chroma(
            collection_name=collection,
            embedding_function=self._embeddings,
            persist_directory=persist_dir,
        )

        logger.info(f"LangChainRAG initialized: {collection} at {persist_dir}")

    def ingest_texts(self, texts: List[str], *, source: str = "manual") -> int:
        """Ingest texts with chunking via RecursiveCharacterTextSplitter."""
        from langchain.text_splitter import RecursiveCharacterTextSplitter

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
        )

        all_chunks = []
        all_metadatas = []
        all_ids = []

        for text in texts:
            chunks = splitter.split_text(text)
            for chunk in chunks:
                all_chunks.append(chunk)
                all_metadatas.append({"source": source})
                all_ids.append(str(uuid.uuid4()))

        if all_chunks:
            self._vectorstore.add_texts(
                texts=all_chunks,
                metadatas=all_metadatas,
                ids=all_ids,
            )

        logger.info(
            f"LangChainRAG ingested {len(all_chunks)} chunks from {len(texts)} texts"
        )
        return len(all_chunks)

    def ingest_folder(self, folder: str) -> int:
        """Ingest all .txt files from a folder."""
        folder_path = Path(folder)
        if not folder_path.exists():
            logger.warning(f"Folder {folder} does not exist.")
            return 0

        texts: List[str] = []
        for p in folder_path.rglob("*.txt"):
            try:
                texts.append(p.read_text(encoding="utf-8", errors="ignore"))
            except Exception as e:
                logger.error(f"Failed to read {p}: {e}")

        if texts:
            return self.ingest_texts(texts, source=f"folder:{folder}")  # noqa: E231
        return 0

    def search(self, query: str, k: int = 5) -> dict:
        """Search and return results in the same format as VectorRAG/AdvancedRAG."""
        results = self._vectorstore.similarity_search_with_score(query, k=k)

        out = []
        for doc, score in results:
            out.append(
                {
                    "text": doc.page_content,
                    "meta": doc.metadata,
                    "score": float(score),
                }
            )

        return {"ok": True, "query": query, "results": out}
