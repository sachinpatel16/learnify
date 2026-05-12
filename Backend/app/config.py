import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from langchain_ollama import ChatOllama
from langchain_openai import OpenAIEmbeddings

load_dotenv()
if not os.getenv("DATABASE_URL"):
    load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# SQLAlchemy pool (production-friendly defaults)
DATABASE_POOL_SIZE = int(os.getenv("DATABASE_POOL_SIZE", "5"))
DATABASE_MAX_OVERFLOW = int(os.getenv("DATABASE_MAX_OVERFLOW", "10"))
DATABASE_POOL_RECYCLE = int(os.getenv("DATABASE_POOL_RECYCLE", "280"))

# CORS: comma-separated origins; use "*" alone for permissive dev (avoid with credentials in browsers)


def parse_allowed_origins() -> list[str]:
    raw = (os.getenv("ALLOWED_ORIGINS") or "*").strip()
    if raw == "*":
        return ["*"]
    parts = [o.strip() for o in raw.split(",") if o.strip()]
    return parts or ["*"]


ALLOWED_ORIGINS = parse_allowed_origins()

# Parallel multi-collection RAG query
RAG_QUERY_MAX_WORKERS = int(os.getenv("RAG_QUERY_MAX_WORKERS", "8"))

# RAG / LLM configuration (env-tunable, sensible defaults)
# CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-oss-120b:clude")
CHAT_MAX_TOKENS = int(os.getenv("CHAT_MAX_TOKENS", "1000"))
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-ada-002")
EXAM_GEN_MAX_WORKERS = int(os.getenv("EXAM_GEN_MAX_WORKERS", "8"))
EXAM_CHAPTER_CACHE_TTL_SECONDS = int(os.getenv("EXAM_CHAPTER_CACHE_TTL_SECONDS", "300"))
EXAM_CHAPTER_CACHE_MAX_ITEMS = int(os.getenv("EXAM_CHAPTER_CACHE_MAX_ITEMS", "64"))

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
CHROMA_DIR = os.getenv("CHROMA_DIR", "chroma_db")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(CHROMA_DIR, exist_ok=True)

UTC = timezone.utc


def now_utc() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(UTC)


def get_embeddings() -> OpenAIEmbeddings:
    """Embedding model used for both ingestion and retrieval."""
    return OpenAIEmbeddings(model=EMBEDDING_MODEL, api_key=OPENAI_API_KEY)


def get_chat_model() -> ChatOllama:
    """Chat LLM used to generate answers from retrieved context.

    Backed by a local Ollama instance, so no remote API credentials are needed.
    """
    return ChatOllama(model="gpt-oss:120b-cloud")
