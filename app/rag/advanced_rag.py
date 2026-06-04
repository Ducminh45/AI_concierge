"""
Advanced RAG Implementation for Monster Resort Concierge
========================================================

This module provides hybrid search (BM25 + dense embeddings) and
cross-encoder reranking for improved retrieval accuracy.

Key Features:
- Hybrid search combining keyword (BM25) and semantic (embeddings) search
- Two-stage reranking with BGE cross-encoder
- Reciprocal Rank Fusion for combining results
- Production-ready with caching and error handling

"""

from typing import List, Dict, Optional, Tuple
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder
from .vector_rag import VectorRAG
from ..monitoring.logging_utils import logger
from ..database.cache_utils import cache_response


class AdvancedRAG(VectorRAG):
    """
    Enhanced RAG with hybrid search and reranking.

    Architecture:
    1. Hybrid Retrieval: BM25 (keyword) + Dense Embeddings (semantic)
    2. Reciprocal Rank Fusion: Combines both result sets
    3. Cross-Encoder Reranking: BGE reranker for final ranking
    """

    def __init__(
        self,
        persist_dir: str,
        collection: str,
        embedding_model: str = "all-MiniLM-L6-v2",
        reranker_model: str = "BAAI/bge-reranker-base",
        ingestion_token: str | None = None,
        enable_anomaly_detection: bool = False,
    ):
        super().__init__(
            persist_dir,
            collection,
            embedding_model,
            ingestion_token=ingestion_token,
            enable_anomaly_detection=enable_anomaly_detection,
        )

        # BM25 components
        self.corpus: List[str] = []
        self.bm25: Optional[BM25Okapi] = None

        # Reranker (lazy loading to save memory)
        self.reranker: Optional[CrossEncoder] = None
        self.reranker_model = reranker_model

        logger.info(
            f"AdvancedRAG initialized with {embedding_model} + {reranker_model}"
        )

        # BM25 is built lazily on first search (not at startup) for performance

    def _rebuild_bm25_from_store(self):
        """Rebuild BM25 index from existing ChromaDB documents."""
        all_docs = self.collection.get()
        docs = all_docs.get("documents", [])
        if docs:
            self.corpus = docs
            tokenized = [doc.lower().split() for doc in docs]
            self.bm25 = BM25Okapi(tokenized)
            logger.info(f"Built BM25 index with {len(docs)} documents")

    def _load_reranker(self):
        """Lazy load reranker to save memory until needed. Gracefully handles low-memory environments."""
        if self.reranker is None:
            try:
                logger.info(f"Attempting to load CrossEncoder reranker model: {self.reranker_model}")
                self.reranker = CrossEncoder(self.reranker_model)
                logger.info("Successfully loaded CrossEncoder reranker.")
            except Exception as e:
                logger.error(
                    f"Failed to load reranker '{self.reranker_model}' due to memory or system limit constraints ({e}). "
                    "Reranking stage will be bypassed."
                )
                self.reranker = None

    def ingest_texts(
        self,
        texts: List[str],
        *,
        source: str = "manual",
        sources: Optional[List[str]] = None,
        token: Optional[str] = None,
    ) -> int:
        """
        Ingest texts and build both dense and BM25 indices.

        Args:
            texts: List of text documents
            source: Source identifier
            sources: Per-document source identifiers
            token: Ingestion authorization token

        Returns:
            Number of documents ingested
        """
        # Store in vector DB (parent class)
        count = super().ingest_texts(texts, source=source, sources=sources, token=token)

        # Build BM25 index
        self.corpus.extend(texts)
        tokenized_corpus = [doc.lower().split() for doc in self.corpus]
        self.bm25 = BM25Okapi(tokenized_corpus)

        logger.info(f"Built BM25 index with {len(self.corpus)} documents")
        return count

    # ingest_folder inherited from VectorRAG — handles chunking and dedup

    def _bm25_search(self, query: str, k: int = 20) -> List[Tuple[int, float]]:
        """
        BM25 keyword search.

        Args:
            query: Search query
            k: Number of results

        Returns:
            List of (doc_index, score) tuples
        """
        if self.bm25 is None:
            self._rebuild_bm25_from_store()
        if self.bm25 is None:
            logger.warning("BM25 index not built, returning empty results")
            return []

        tokenized_query = query.lower().split()
        scores = self.bm25.get_scores(tokenized_query)

        # Get top-k with positive scores
        import numpy as np

        top_indices = np.argsort(scores)[::-1][:k]
        return [
            (int(idx), float(scores[idx])) for idx in top_indices if scores[idx] > 0
        ]

    def _dense_search(self, query: str, k: int = 20) -> List[Tuple[str, float]]:
        """Dense embedding search via ChromaDB directly."""
        try:
            results = self.collection.query(query_texts=[query], n_results=k)
            docs = results.get("documents", [[]])[0]
            scores = results.get("distances", [[]])[0]
            return [(doc, float(score)) for doc, score in zip(docs, scores)]
        except Exception:
            return []

    def _reciprocal_rank_fusion(
        self,
        bm25_results: List[Tuple[int, float]],
        dense_results: List[Tuple[str, float]],
        k: int = 60,
        bm25_weight: float = 0.4,
    ) -> List[Dict]:
        """
        Combine BM25 and dense results using Reciprocal Rank Fusion.

        Formula: score = sum(1 / (k + rank)) for each result list

        Args:
            bm25_results: BM25 (index, score) results
            dense_results: Dense (text, score) results
            k: RRF constant (typically 60)
            bm25_weight: Weight for BM25 scores (0-1)

        Returns:
            Fused and ranked documents with scores
        """
        scores = {}

        # BM25 scores
        for rank, (idx, _) in enumerate(bm25_results):
            doc = self.corpus[idx]
            scores[doc] = scores.get(doc, 0) + bm25_weight * (1 / (k + rank))

        # Dense scores
        dense_weight = 1 - bm25_weight
        for rank, (doc, _) in enumerate(dense_results):
            scores[doc] = scores.get(doc, 0) + dense_weight * (1 / (k + rank))

        # Sort by combined score
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [{"text": doc, "score": score} for doc, score in ranked]

    def _rerank(self, query: str, documents: List[Dict], top_k: int = 5) -> List[Dict]:
        """
        Rerank documents using cross-encoder.

        Args:
            query: Search query
            documents: Candidate documents as {text, score} dicts
            top_k: Number of final results

        Returns:
            List of reranked documents with scores
        """
        if not documents:
            return []

        # Lazy load reranker
        self._load_reranker()

        if self.reranker is None:
            logger.warning("Reranker is not available. Bypassing reranker stage and returning hybrid search results directly.")
            return documents[:top_k]

        # Score all pairs
        texts = [doc["text"] for doc in documents]
        pairs = [[query, text] for text in texts]
        scores = self.reranker.predict(pairs)

        # Sort and return top-k
        import numpy as np

        sorted_indices = np.argsort(scores)[::-1][:top_k]
        return [{"text": texts[i], "score": float(scores[i])} for i in sorted_indices]

    @cache_response(ttl=300)
    def search(
        self,
        query: str,
        k: int = 5,
        hybrid_k: int = 20,
        bm25_weight: float = 0.4,
        use_reranker: bool = True,
    ) -> Dict:
        """
        Hybrid search with optional reranking.

        Args:
            query: Search query
            k: Number of final results
            hybrid_k: Number of candidates before reranking
            bm25_weight: Weight for BM25 in RRF
            use_reranker: Whether to rerank with cross-encoder

        Returns:
            Dict with 'results' (list of {text, score})
        """
        # Prioritize JSON database search for production collection
        from ..config import get_settings
        settings = get_settings()
        if self.collection_name == settings.rag_collection:
            json_results = self.search_json_db(query, k)
            if json_results and json_results.get("results"):
                # Format to match expectations: return {"results": results}
                return {"results": json_results["results"]}

        # 1. Retrieve candidates
        bm25_results = self._bm25_search(query, k=hybrid_k)
        dense_results = self._dense_search(query, k=hybrid_k)

        # 2. Fuse results
        fused_docs = self._reciprocal_rank_fusion(
            bm25_results, dense_results, k=60, bm25_weight=bm25_weight
        )

        # 3. Rerank (optional)
        if use_reranker:
            reranked = self._rerank(query, fused_docs, top_k=k)
            return {"results": reranked}
        else:
            # Return top-k fused docs with real fusion scores
            return {"results": fused_docs[:k]}


# Convenience function for easy migration
def create_advanced_rag(persist_dir: str, collection: str) -> AdvancedRAG:
    """
    Factory function to create AdvancedRAG instance.

    Usage:
        from app.advanced_rag import create_advanced_rag
        rag = create_advanced_rag(".rag_store", "knowledge")
    """
    return AdvancedRAG(persist_dir, collection)
