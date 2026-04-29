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

# RAG / LLM configuration (env-tunable, sensible defaults)
# CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-oss-120b:clude")
CHAT_MAX_TOKENS = int(os.getenv("CHAT_MAX_TOKENS", "1000"))
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-ada-002")

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
