"""HTTP API for the RAG pipeline: upload, process, list, query, delete."""

import os
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.orm import Session

from app.config import UPLOAD_DIR, get_chat_model
from app.database import get_db
from app.logger import get_logger
from app.models import Document
from app.response import (
    MSG_DOC_DELETED,
    MSG_DOC_PROCESSED,
    MSG_DOC_UPLOADED,
    MSG_FETCHED,
    MSG_QUERY_SUCCESS,
    success_response,
)
from app.schemas import DocumentResponse, QueryRequest
from app.utils import SUPPORTED_EXTENSIONS, rag_pipeline

logger = get_logger(__name__)

router = APIRouter(prefix="/rag", tags=["RAG"])


# ── Helpers ──────────────────────────────────────────────────────────────────


def _get_document_or_404(db: Session, doc_id: str) -> Document:
    document = db.query(Document).filter(Document.id == doc_id).first()
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


def _doc_payload(document: Document) -> dict:
    return DocumentResponse.model_validate(document).model_dump(mode="json")


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/documents", status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload a *loose* (no-book) document for the legacy ``/rag/query`` flow.

    For per-chapter uploads attached to a Book, use
    ``POST /rag/books/{book_id}/chapters`` instead.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file type '{ext}'. "
                f"Allowed: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            ),
        )

    doc_id = str(uuid.uuid4())
    safe_name = f"{doc_id}{ext}"
    saved_path = os.path.join(UPLOAD_DIR, safe_name)

    try:
        contents = await file.read()
        with open(saved_path, "wb") as out:
            out.write(contents)
    except Exception as e:
        logger.error(f"Failed to save uploaded file '{file.filename}': {e}")
        raise HTTPException(status_code=500, detail="Failed to save uploaded file") from e

    document = Document(
        id=doc_id,
        filename=file.filename,
        path=saved_path,
        is_processed=False,
        status="pending",
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    return success_response(data=_doc_payload(document), message=MSG_DOC_UPLOADED)


@router.post("/documents/{doc_id}/process")
def process_uploaded_document(doc_id: str, db: Session = Depends(get_db)):
    """Embed the document into ChromaDB and mark it processed."""
    document = _get_document_or_404(db, doc_id)

    document.status = "processing"
    document.error_message = None
    db.commit()

    try:
        namespace = rag_pipeline.process(
            filepath=document.path,
            doc_id=document.id,
            chapter_number=document.chapter_number,
            chapter_title=document.chapter_title,
        )
    except FileNotFoundError as e:
        document.status = "failed"
        document.error_message = str(e)
        db.commit()
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        document.status = "failed"
        document.error_message = str(e)
        db.commit()
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("Failed to process document %s", doc_id)
        document.status = "failed"
        document.error_message = str(e)
        db.commit()
        raise HTTPException(status_code=500, detail="Failed to process document") from e

    document.vector_namespace = namespace
    document.is_processed = True
    document.status = "completed"
    db.commit()
    db.refresh(document)

    return success_response(data=_doc_payload(document), message=MSG_DOC_PROCESSED)


@router.get("/documents")
def list_documents(db: Session = Depends(get_db)):
    """List all documents tracked by the RAG pipeline (newest first)."""
    documents = db.query(Document).order_by(Document.created_at.desc()).all()
    payload = [_doc_payload(d) for d in documents]
    return success_response(data=payload, message=MSG_FETCHED)


@router.post("/query")
def query_documents(payload: QueryRequest, db: Session = Depends(get_db)):
    """Retrieve relevant context from processed documents and generate an answer."""
    documents = _resolve_query_targets(db, payload.document_ids)
    namespaces = [d.vector_namespace for d in documents if d.vector_namespace]

    context: Optional[str] = rag_pipeline.query(
        question=payload.question, namespaces=namespaces
    )
    context_found = context is not None

    if context_found:
        system_message = rag_pipeline.build_system_message(context or "")
    else:
        system_message = (
            "You are a helpful assistant. The user's question could not be answered "
            "from the available documents; tell the user you do not have that information."
        )

    try:
        llm = get_chat_model()
        response = llm.invoke(
            [SystemMessage(content=system_message), HumanMessage(content=payload.question)]
        )
        answer = getattr(response, "content", str(response))
    except Exception as e:
        logger.exception("LLM invocation failed")
        raise HTTPException(status_code=502, detail="Failed to generate answer") from e

    data = {
        "answer": answer,
        "context_found": context_found,
        "used_documents": [d.id for d in documents] if context_found else [],
    }
    return success_response(data=data, message=MSG_QUERY_SUCCESS)


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: str, db: Session = Depends(get_db)):
    """Delete the Chroma collection, the file on disk, and the DB row."""
    document = _get_document_or_404(db, doc_id)

    if document.vector_namespace:
        rag_pipeline.delete_collection(document.vector_namespace)

    if document.path and os.path.exists(document.path):
        try:
            os.remove(document.path)
        except OSError as e:
            logger.warning(f"Failed to remove file '{document.path}': {e}")

    db.delete(document)
    db.commit()

    return success_response(data=None, message=MSG_DOC_DELETED)


def _resolve_query_targets(db: Session, document_ids: Optional[list[str]]) -> list[Document]:
    """Return processed documents to query, scoped by ``document_ids`` when provided."""
    query = db.query(Document).filter(Document.is_processed.is_(True))
    if document_ids:
        query = query.filter(Document.id.in_(document_ids))
        documents = query.all()
        missing = set(document_ids) - {d.id for d in documents}
        if missing:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown or unprocessed document(s): {sorted(missing)}",
            )
        return documents
    return query.all()
