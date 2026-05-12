"""RAG pipeline: document loading, chunking (chapter-aware when applicable), embedding, retrieval."""

import collections
import concurrent.futures
import hashlib
import os
import time
from typing import Callable, Optional

import chromadb
from langchain_chroma import Chroma
from langchain_community.document_loaders import (
    BSHTMLLoader,
    CSVLoader,
    Docx2txtLoader,
    JSONLoader,
    PyMuPDFLoader,
    TextLoader,
    UnstructuredMarkdownLoader,
    UnstructuredRTFLoader,
)
from langchain_core.documents import Document as LCDocument
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import (
    CHROMA_DIR,
    EXAM_CHAPTER_CACHE_MAX_ITEMS,
    EXAM_CHAPTER_CACHE_TTL_SECONDS,
    RAG_QUERY_MAX_WORKERS,
    get_embeddings,
)
from app.logger import get_logger

logger = get_logger(__name__)


SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".csv",
    ".txt",
    ".doc",
    ".docx",
    ".md",
    ".rtf",
    ".json",
    ".html",
}

RAG_SYSTEM_PROMPT = (
    "You are a professional company chatbot.\n\n"
    "Rules:\n"
    "- Answer briefly (maximum 4-5 lines).\n"
    "- Keep responses clear and simple.\n"
    "- Do not give detailed explanations.\n"
    "- Give direct answers only.\n"
    "- If the answer is not in the context, say you do not have that information.\n\n"
    "Context:\n{rag_context}"
)


def _load_json_with_fallback(filepath: str) -> list:
    """Try ``JSONLoader`` (requires jq); fall back to plain text on failure."""
    try:
        return JSONLoader(file_path=filepath, jq_schema=".", text_content=False).load()
    except Exception:
        return TextLoader(filepath, encoding="utf-8").load()


class RagPipeline:
    """End-to-end RAG pipeline backed by ChromaDB."""

    _LOADERS: dict[str, Callable[[str], list]] = {
        ".pdf": lambda p: PyMuPDFLoader(p, extract_tables="markdown").load(),
        ".csv": lambda p: CSVLoader(file_path=p).load(),
        ".txt": lambda p: TextLoader(p, encoding="utf-8").load(),
        ".doc": lambda p: Docx2txtLoader(p).load(),
        ".docx": lambda p: Docx2txtLoader(p).load(),
        ".md": lambda p: UnstructuredMarkdownLoader(p).load(),
        ".rtf": lambda p: UnstructuredRTFLoader(p).load(),
        ".html": lambda p: BSHTMLLoader(p).load(),
        ".json": _load_json_with_fallback,
    }

    def __init__(
        self,
        chroma_dir: str = CHROMA_DIR,
        chunk_size: int = 1200,
        chunk_overlap: int = 150,
        top_k: int = 5,
        score_threshold: float = 0.65,
    ) -> None:
        self.chroma_dir = chroma_dir
        self.top_k = top_k
        self.score_threshold = score_threshold

        self._client = chromadb.PersistentClient(path=chroma_dir)
        self._embeddings = get_embeddings()
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            add_start_index=True,
        )
        self._chapter_text_cache: collections.OrderedDict[
            tuple[str, int], tuple[float, str]
        ] = collections.OrderedDict()

    # ── Public API ──────────────────────────────────────────────────────────

    @staticmethod
    def collection_name_for(doc_id: str) -> str:
        """Generate a short, safe ChromaDB collection name for a document."""
        doc_hash = hashlib.md5(str(doc_id).encode()).hexdigest()[:8]
        return f"doc-{doc_hash}"

    def process(
        self,
        filepath: str,
        doc_id: str,
        chapter_number: Optional[int] = None,
        chapter_title: Optional[str] = None,
    ) -> str:
        """Embed a document into its own ChromaDB collection.

        When ``chapter_number`` is supplied, every chunk is tagged with
        ``chapter_number`` / ``chapter_title`` so the exam generator can
        pull the chapter back via ``get_chapter_text``. When omitted, the
        document is treated as a freeform RAG file (no chapter metadata).

        Returns the collection name (vector namespace).
        """
        collection_name = self.collection_name_for(doc_id)
        logger.info(f"Processing document doc={doc_id} -> collection={collection_name}")

        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Document file not found at path: {filepath}")

        if self._collection_has_vectors(collection_name):
            logger.info(
                f"Collection {collection_name} already populated, skipping re-embedding"
            )
            return collection_name

        try:
            chunks = self._build_chunks(
                filepath=filepath,
                doc_id=doc_id,
                chapter_number=chapter_number,
                chapter_title=chapter_title,
            )
        except Exception as e:
            logger.error(f"Failed to load/chunk document '{filepath}': {e}")
            raise ValueError(f"Could not read document file: {e}") from e

        if not chunks:
            raise ValueError("Document appears to be empty or unreadable")

        logger.info(
            f"Split into {len(chunks)} chunk(s) for collection: {collection_name}"
        )

        try:
            Chroma.from_documents(
                documents=chunks,
                embedding=self._embeddings,
                collection_name=collection_name,
                persist_directory=self.chroma_dir,
            )
        except Exception as e:
            logger.error(
                f"Failed to embed document into collection '{collection_name}': {e}"
            )
            raise

        logger.info(f"Successfully embedded document into collection: {collection_name}")
        return collection_name

    def get_chapter_text(self, namespace: str, chapter_number: int) -> str:
        """Return the full text of one chapter, reassembled from its chunks.

        For chapter documents this is just every chunk in the collection,
        ordered by ``start_index`` (the splitter's offset within the chapter
        text). When the chunks were tagged with ``chapter_number`` we filter
        on it; otherwise we fall back to returning everything in the
        collection.
        """
        if not namespace:
            return ""
        cache_key = (namespace, int(chapter_number))
        now = time.time()
        cached = self._chapter_text_cache.get(cache_key)
        if cached is not None:
            expires_at, cached_text = cached
            if now < expires_at:
                self._chapter_text_cache.move_to_end(cache_key)
                return cached_text
            self._chapter_text_cache.pop(cache_key, None)
        try:
            collection = self._client.get_collection(name=namespace)
        except ValueError:
            logger.warning(f"Collection '{namespace}' not found")
            return ""
        except Exception as e:
            logger.error(f"Could not open collection '{namespace}': {e}")
            return ""

        try:
            result = collection.get(where={"chapter_number": int(chapter_number)})
            docs = result.get("documents") or []
            metas = result.get("metadatas") or [{} for _ in docs]
            if not docs:
                # Fallback: collection isn't tagged (or wrong chapter); pull all.
                result = collection.get()
                docs = result.get("documents") or []
                metas = result.get("metadatas") or [{} for _ in docs]
        except Exception as e:
            logger.error(
                f"Failed to fetch chapter {chapter_number} from '{namespace}': {e}"
            )
            return ""

        pairs = list(zip(docs, metas))
        pairs.sort(key=lambda p: (p[1] or {}).get("start_index", 0))
        chapter_text = "\n\n".join(text for text, _ in pairs if text)
        self._chapter_text_cache[cache_key] = (
            now + max(1, EXAM_CHAPTER_CACHE_TTL_SECONDS),
            chapter_text,
        )
        self._chapter_text_cache.move_to_end(cache_key)
        max_items = max(1, EXAM_CHAPTER_CACHE_MAX_ITEMS)
        while len(self._chapter_text_cache) > max_items:
            self._chapter_text_cache.popitem(last=False)
        return chapter_text

    def query(
        self,
        question: str,
        namespaces: list[str],
        top_k: Optional[int] = None,
        score_threshold: Optional[float] = None,
    ) -> Optional[str]:
        """Retrieve relevant context from the given Chroma collections."""
        if not namespaces:
            logger.info("No active namespaces/collections to query")
            return None

        k = top_k if top_k is not None else self.top_k
        threshold = score_threshold if score_threshold is not None else self.score_threshold

        max_workers = min(len(namespaces), max(1, RAG_QUERY_MAX_WORKERS))

        def _hit(ns: str) -> Optional[str]:
            return self._query_namespace(question, ns, k, threshold)

        if max_workers <= 1 or len(namespaces) == 1:
            all_contexts = [ctx for ctx in (_hit(ns) for ns in namespaces) if ctx]
        else:
            results: list[Optional[str]] = [None] * len(namespaces)
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_index = {
                    executor.submit(_hit, namespaces[i]): i for i in range(len(namespaces))
                }
                for fut in concurrent.futures.as_completed(future_index):
                    idx = future_index[fut]
                    try:
                        results[idx] = fut.result()
                    except Exception as e:
                        logger.error(
                            "Parallel query failed for namespace %s: %s",
                            namespaces[idx],
                            e,
                        )
                        results[idx] = None
            all_contexts = [ctx for ctx in results if ctx]

        if not all_contexts:
            return None
        if len(all_contexts) == 1:
            return all_contexts[0]
        return "\n\n---\n\n".join(all_contexts)

    def delete_collection(self, collection_name: str) -> None:
        """Best-effort delete of a ChromaDB collection."""
        if not collection_name:
            return
        try:
            self._client.delete_collection(name=collection_name)
            logger.info(f"Deleted ChromaDB collection: {collection_name}")
        except ValueError:
            logger.warning(
                f"Collection '{collection_name}' does not exist, ignoring delete"
            )
        except Exception as e:
            logger.error(f"Error deleting collection '{collection_name}': {e}")

    @staticmethod
    def build_system_message(rag_context: str) -> str:
        """Render the RAG system prompt with retrieved context injected."""
        return RAG_SYSTEM_PROMPT.replace("{rag_context}", rag_context or "")

    # ── Private helpers ─────────────────────────────────────────────────────

    def _build_chunks(
        self,
        filepath: str,
        doc_id: str,
        chapter_number: Optional[int],
        chapter_title: Optional[str],
    ) -> list[LCDocument]:
        """Chunk a document, attaching chapter metadata when supplied."""
        documents = self._load(filepath)
        if not documents:
            return []

        chunks = self._splitter.split_documents(documents)

        base_meta: dict = {"doc_id": doc_id}
        if chapter_number is not None:
            base_meta["chapter_number"] = int(chapter_number)
        if chapter_title:
            base_meta["chapter_title"] = str(chapter_title)

        for ch in chunks:
            ch.metadata = {**(ch.metadata or {}), **base_meta}
        return chunks

    def _load(self, filepath: str) -> list:
        """Pick the appropriate LangChain loader based on the file extension."""
        ext = os.path.splitext(filepath)[1].lower()
        loader = self._LOADERS.get(ext)
        if loader is None:
            raise ValueError(
                f"Unsupported file type: '{ext}'. "
                f"Allowed: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            )
        return loader(filepath)

    def _collection_has_vectors(self, collection_name: str) -> bool:
        try:
            collection = self._client.get_collection(name=collection_name)
            return collection.count() > 0
        except ValueError:
            return False
        except Exception as e:
            # Chroma can raise non-ValueError exceptions when a collection is missing.
            # Missing collection on first ingest is expected, so treat it as "no vectors"
            # without polluting logs with warnings.
            error_text = str(e).lower()
            if "does not exist" in error_text or "not found" in error_text:
                return False
            logger.warning(
                f"Could not check collection stats for '{collection_name}': {e}"
            )
            return False

    def _query_namespace(
        self,
        question: str,
        namespace: str,
        top_k: int,
        score_threshold: float,
    ) -> Optional[str]:
        """Retrieve relevant chunks from a single Chroma collection."""
        try:
            if not self._collection_has_vectors(namespace):
                logger.warning(f"Collection '{namespace}' is empty or missing, skipping")
                return None

            vector_store = Chroma(
                collection_name=namespace,
                embedding_function=self._embeddings,
                persist_directory=self.chroma_dir,
            )

            fetch_k = top_k * 3

            scored_results = vector_store.similarity_search_with_relevance_scores(
                question, k=fetch_k
            )
            score_map = {doc.page_content: score for doc, score in scored_results}

            retriever = vector_store.as_retriever(
                search_type="mmr",
                search_kwargs={"k": top_k, "fetch_k": fetch_k, "lambda_mult": 0.7},
            )
            mmr_docs = retriever.invoke(question)

            docs = [
                doc
                for doc in mmr_docs
                if score_map.get(doc.page_content, 0) >= score_threshold
            ]

            if not docs:
                logger.info(
                    f"No chunks met score threshold ({score_threshold}) "
                    f"in collection: {namespace}"
                )
                return None

            logger.info(
                f"Retrieved {len(docs)} chunk(s) above threshold ({score_threshold}) "
                f"from collection '{namespace}'"
            )
            return "\n\n".join(doc.page_content for doc in docs)
        except Exception as e:
            logger.error(f"Error querying collection '{namespace}': {e}")
            return None


rag_pipeline = RagPipeline()
