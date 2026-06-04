import hashlib
import re
import time
import numpy as np
from typing import Iterable, List, Optional
from ..monitoring.metrics import Counter

RAG_HIT_COUNT = Counter("mrc_rag_hits_total", "Total RAG search hits")

# --- Vector-based RAG using ChromaDB and HuggingFace embeddings ---
import os  # noqa: E402
os.environ["ANONYMIZED_TELEMETRY"] = "false"  # Disable ChromaDB telemetry (posthog fix)
import chromadb  # noqa: E402
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction  # noqa: E402
from pathlib import Path  # noqa: E402
from ..monitoring.logging_utils import logger, AIServiceError  # noqa: E402
from ..monitoring.profile_utils import profile  # noqa: E402
from ..database.cache_utils import cache_response  # noqa: E402


_RAG_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"SYSTEM\s*:",
        r"###\s*INSTRUCTION",
        r"ignore\s+(all\s+)?previous\s+instructions",
        r"you\s+are\s+now\s+(?:a|an|the)\b",
        r"\[INST\]",
        r"<<SYS>>",
    ]
]


class VectorRAG:
    def __init__(
        self,
        persist_dir: str,
        collection: str,
        embedding_model: str = "all-MiniLM-L6-v2",
        ingestion_token: Optional[str] = None,
        enable_anomaly_detection: bool = False,
    ):
        """
        Initialize VectorRAG with HuggingFace embeddings (compatible with ChromaDB 0.5.23).

        Args:
            persist_dir: Directory to persist ChromaDB data
            collection: Name of the collection
            embedding_model: HuggingFace model name (default: all-MiniLM-L6-v2)
            ingestion_token: Defense 3 — token required for ingestion operations
        """
        self.persist_dir = persist_dir
        self.collection_name = collection
        self.embedding_model = embedding_model
        self._ingestion_token = ingestion_token
        self._anomaly_detection = enable_anomaly_detection

        # Initialize ChromaDB client
        self.chroma_client = chromadb.PersistentClient(path=persist_dir)

        # Create or get collection with HuggingFace embeddings
        self.collection = self.chroma_client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=SentenceTransformerEmbeddingFunction(
                model_name=self.embedding_model
            ),
        )

    @staticmethod
    def _chunk_text(text: str, chunk_size: int = 600, overlap: int = 100) -> List[str]:
        """
        Split text into overlapping chunks by paragraph boundaries.

        Args:
            text: Full text to chunk
            chunk_size: Target chunk size in characters
            overlap: Number of overlapping characters between chunks

        Returns:
            List of text chunks
        """
        text = text.strip()
        if not text:
            return []
        if len(text) <= chunk_size:
            return [text]

        # Split on double newlines (paragraphs)
        paragraphs = re.split(r"\n\s*\n", text)
        paragraphs = [p.strip() for p in paragraphs if p.strip()]

        chunks = []
        current = ""

        for para in paragraphs:
            # If single paragraph exceeds chunk_size, split on sentences
            if len(para) > chunk_size:
                sentences = re.split(r"(?<=[.!?])\s+", para)
                for sent in sentences:
                    if len(current) + len(sent) + 1 > chunk_size and current:
                        chunks.append(current.strip())
                        # Start new chunk with overlap from end of previous
                        current = current[-overlap:] + " " + sent if overlap else sent
                    else:
                        current = current + " " + sent if current else sent
                continue

            if len(current) + len(para) + 2 > chunk_size and current:
                chunks.append(current.strip())
                # Start new chunk with overlap from end of previous
                current = current[-overlap:] + "\n\n" + para if overlap else para
            else:
                current = current + "\n\n" + para if current else para

        if current.strip():
            chunks.append(current.strip())

        return chunks

    @staticmethod
    def _sanitize_chunk(text: str) -> str:
        """Strip injection patterns from a text chunk before ingestion.

        Removes suspicious portions (system instructions, prompt injections)
        rather than discarding the entire chunk.
        """
        sanitized = text
        for pattern in _RAG_INJECTION_PATTERNS:
            match = pattern.search(sanitized)
            if match:
                logger.warning(
                    "rag_chunk_injection_stripped",
                    extra={
                        "pattern": pattern.pattern,
                        "preview": sanitized[max(0, match.start() - 20):match.end() + 20],
                    },
                )
                sanitized = pattern.sub("", sanitized)
        return sanitized.strip()

    def _check_ingestion_auth(self, token: Optional[str] = None):
        """Defense 3: Verify ingestion token before allowing writes."""
        if self._ingestion_token and token != self._ingestion_token:
            logger.warning("rag_ingestion_unauthorized", extra={"token_provided": bool(token)})
            raise AIServiceError("Unauthorized ingestion attempt — valid token required.")

    def _check_embedding_anomaly(self, texts: List[str], threshold: float = 3.0) -> List[bool]:
        """Defense 5: Flag texts whose embeddings are statistical outliers."""
        if self.collection.count() < 10:
            return [False] * len(texts)

        try:
            existing = self.collection.get(include=["embeddings"], limit=500)
            existing_embs = np.array(existing.get("embeddings", []))

            if len(existing_embs) == 0:
                return [False] * len(texts)

            centroid = existing_embs.mean(axis=0)
            distances = np.linalg.norm(existing_embs - centroid, axis=1)
            mean_dist = float(distances.mean())
            std_dist = float(distances.std())

            # Embed new texts using ChromaDB's embedding function
            ef = SentenceTransformerEmbeddingFunction(model_name=self.embedding_model)
            new_embs = np.array(ef(texts))
            new_distances = np.linalg.norm(new_embs - centroid, axis=1)

            return [float(d) > mean_dist + threshold * std_dist for d in new_distances]
        except Exception as e:
            logger.warning(f"Anomaly detection failed, allowing ingestion: {e}")
            return [False] * len(texts)

    def ingest_texts(
        self,
        texts: Iterable[str],
        *,
        source: str = "manual",
        sources: Optional[List[str]] = None,
        token: Optional[str] = None,
    ) -> int:
        """
        Ingest texts into the vector database using content-hash IDs (idempotent).

        Args:
            texts: Iterable of text strings to ingest
            source: Source identifier for metadata (used if sources not provided)
            sources: Per-document source identifiers
            token: Defense 3 — ingestion authorization token

        Returns:
            Number of documents ingested
        """
        # Defense 3: Check ingestion authorization
        self._check_ingestion_auth(token)

        text_list = list(texts)
        if not text_list:
            return 0

        # Defense 5: Check for anomalous embeddings
        if self._anomaly_detection:
            anomalies = self._check_embedding_anomaly(text_list)
        else:
            anomalies = [False] * len(text_list)

        now = time.time()
        if sources:
            metadatas = [{"source": s} for s in sources]
        else:
            metadatas = [{"source": source} for _ in text_list]

        # Defense 6: Sanitize chunks to strip injected instructions
        text_list = [self._sanitize_chunk(t) for t in text_list]
        # Remove any chunks that became empty after sanitisation
        filtered = [
            (t, m, a)
            for t, m, a in zip(text_list, metadatas, anomalies)
            if t
        ]
        if not filtered:
            return 0
        text_list, metadatas, anomalies = (
            [x[0] for x in filtered],
            [x[1] for x in filtered],
            [x[2] for x in filtered],
        )

        # Defense 2 & 4: Add content hash, ingestion timestamp, and anomaly flag
        for i, text in enumerate(text_list):
            content_hash = hashlib.sha256(text.encode()).hexdigest()
            metadatas[i]["content_hash"] = content_hash
            metadatas[i]["ingested_at"] = now
            if anomalies[i]:
                metadatas[i]["flagged_anomaly"] = True
                logger.warning(
                    "rag_anomalous_embedding",
                    extra={"source": metadatas[i]["source"], "content_preview": text[:100]},
                )

        # Hash-based IDs for deduplication
        ids = [hashlib.sha256(t.encode()).hexdigest()[:16] for t in text_list]

        try:
            self.collection.upsert(documents=text_list, metadatas=metadatas, ids=ids)
            return len(ids)
        except Exception as e:
            logger.error(f"ChromaDB ingestion failed: {e}")
            raise AIServiceError(f"ChromaDB ingestion failed: {e}")

    def ingest_folder(self, folder: str, token: Optional[str] = None) -> int:
        """
        Ingest all .txt files from a folder, chunked and deduplicated.

        Args:
            folder: Path to folder containing .txt files

        Returns:
            Number of documents ingested (0 if already populated)
        """
        folder_path = Path(folder)
        if not folder_path.exists():
            logger.warning(f"Knowledge folder not found: {folder}")
            return 0

        # Skip if already ingested
        existing = self.collection.count()
        if existing > 0:
            logger.info(f"Collection already has {existing} documents, skipping ingestion")
            return 0

        chunks: List[str] = []
        chunk_sources: List[str] = []

        for p in sorted(folder_path.rglob("*.txt")):
            try:
                content = p.read_text(encoding="utf-8", errors="ignore")
                file_chunks = self._chunk_text(content)
                chunks.extend(file_chunks)
                chunk_sources.extend(
                    [f"{p.name}:chunk_{i}" for i in range(len(file_chunks))]  # noqa: E231
                )
                logger.info(f"Chunked {p.name} into {len(file_chunks)} pieces")
            except Exception as e:
                logger.error(f"Failed to read file {p}: {e}")
                raise AIServiceError(f"Failed to read file {p}: {e}")

        if not chunks:
            return 0

        try:
            return self.ingest_texts(chunks, sources=chunk_sources, token=token)
        except Exception as e:
            logger.error(f"Failed to ingest texts from folder {folder}: {e}")
            raise AIServiceError(f"Failed to ingest texts from folder {folder}: {e}")

    @profile
    @cache_response(ttl=300)
    def search(self, query: str, k: int = 5) -> dict:
        """
        Search the vector database for relevant documents.

        Args:
            query: Search query string
            k: Number of results to return

        Returns:
            Dictionary with search results
        """
        try:
            results = self.collection.query(query_texts=[query], n_results=k)
            docs = results.get("documents", [[]])[0]
            metadatas = results.get("metadatas", [[]])[0]
            scores = results.get("distances", [[]])[0]

            out = []
            for doc, meta, score in zip(docs, metadatas, scores):
                # Defense 2: Verify content integrity
                if meta.get("content_hash"):
                    expected = hashlib.sha256(doc.encode()).hexdigest()
                    if meta["content_hash"] != expected:
                        logger.warning(
                            "rag_integrity_check_failed",
                            extra={"source": meta.get("source", "unknown")},
                        )
                        continue

                # Defense 5: Skip anomaly-flagged chunks
                if meta.get("flagged_anomaly"):
                    logger.info(
                        "rag_skipping_anomalous_chunk",
                        extra={"source": meta.get("source", "unknown")},
                    )
                    continue

                out.append({"text": doc, "meta": meta, "score": float(score)})

            if out:
                RAG_HIT_COUNT.inc()

            return {"ok": True, "query": query, "results": out}
        except Exception as e:
            logger.error(f"ChromaDB search failed: {e}")
            raise AIServiceError(f"ChromaDB search failed: {e}")
