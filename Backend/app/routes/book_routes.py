"""HTTP API for Books and per-chapter document uploads."""

from __future__ import annotations

import os
import uuid
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.config import UPLOAD_DIR
from app.database import get_db
from app.logger import get_logger
from app.models import Book, Document, Exam
from app.response import (
    MSG_BOOK_CREATED,
    MSG_BOOK_DELETED,
    MSG_BOOK_FETCHED,
    MSG_CHAPTER_UPLOADED,
    MSG_FETCHED,
    success_response,
)
from app.schemas import (
    BookCreate,
    BookResponse,
    BookWithChapters,
    ChapterDocumentResponse,
    ExamResponse,
)
from app.utils import SUPPORTED_EXTENSIONS

logger = get_logger(__name__)

router = APIRouter(prefix="/rag", tags=["Books"])


# ── Helpers ──────────────────────────────────────────────────────────────────


def _book_payload(book: Book) -> dict:
    return BookResponse.model_validate(book).model_dump(mode="json")


def _book_with_chapters_payload(book: Book) -> dict:
    return BookWithChapters.model_validate(
        {
            **BookResponse.model_validate(book).model_dump(),
            "chapters": [
                ChapterDocumentResponse.model_validate(d).model_dump() for d in book.chapters
            ],
        }
    ).model_dump(mode="json")


def _chapter_payload(document: Document) -> dict:
    return ChapterDocumentResponse.model_validate(document).model_dump(mode="json")


def _exam_payload(exam: Exam) -> dict:
    return ExamResponse.model_validate(exam).model_dump(mode="json")


def _get_book_or_404(db: Session, book_id: str) -> Book:
    book = db.query(Book).filter(Book.id == book_id).first()
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    return book


# ── Book endpoints ───────────────────────────────────────────────────────────


@router.post("/books", status_code=status.HTTP_201_CREATED)
def create_book(payload: BookCreate, db: Session = Depends(get_db)):
    """Create a new Book (e.g. 'Class 10 Science NCERT')."""
    book = Book(
        title=payload.title.strip(),
        standard=(payload.standard.strip() if payload.standard else None),
        subject=(payload.subject.strip() if payload.subject else None),
        board=(payload.board.strip() if payload.board else None),
        language=(payload.language or "en"),
    )
    db.add(book)
    db.commit()
    db.refresh(book)
    return success_response(data=_book_payload(book), message=MSG_BOOK_CREATED)


@router.get("/books")
def list_books(db: Session = Depends(get_db)):
    """List all books (newest first)."""
    books = db.query(Book).order_by(Book.created_at.desc()).all()
    return success_response(
        data=[_book_payload(b) for b in books], message=MSG_FETCHED
    )


@router.get("/books/{book_id}")
def get_book(book_id: str, db: Session = Depends(get_db)):
    """Return a book with its chapter documents nested."""
    book = _get_book_or_404(db, book_id)
    return success_response(
        data=_book_with_chapters_payload(book), message=MSG_BOOK_FETCHED
    )


@router.delete("/books/{book_id}")
def delete_book(book_id: str, db: Session = Depends(get_db)):
    """Delete a book, all its chapter documents, and any generated exams.

    Removes Chroma collections and uploaded files for each chapter as well.
    """
    book = _get_book_or_404(db, book_id)

    from app.utils import rag_pipeline  # local import avoids cycles at import time

    for chapter in list(book.chapters):
        if chapter.vector_namespace:
            rag_pipeline.delete_collection(chapter.vector_namespace)
        if chapter.path and os.path.exists(chapter.path):
            try:
                os.remove(chapter.path)
            except OSError as e:
                logger.warning(f"Failed to remove file '{chapter.path}': {e}")

    db.delete(book)
    db.commit()
    return success_response(data=None, message=MSG_BOOK_DELETED)


# ── Chapter upload endpoints ─────────────────────────────────────────────────


@router.post(
    "/books/{book_id}/chapters",
    status_code=status.HTTP_201_CREATED,
)
async def upload_chapter(
    book_id: str,
    file: UploadFile = File(...),
    chapter_number: int = Form(..., ge=1),
    chapter_title: str = Form(..., min_length=1),
    display_name: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """Upload one chapter PDF (or other supported file) to a book.

    The user supplies ``chapter_number`` and ``chapter_title``; we never
    auto-detect. A readable ``display_name`` like 'Chapter 5 - Light' is
    auto-built when the caller doesn't provide one.
    """
    book = _get_book_or_404(db, book_id)

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

    existing = (
        db.query(Document)
        .filter(
            Document.book_id == book.id,
            Document.chapter_number == chapter_number,
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Chapter {chapter_number} already exists for this book "
                f"(document {existing.id}). Delete it first or pick a different number."
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

    title_clean = chapter_title.strip()
    readable = (display_name or "").strip() or f"Chapter {chapter_number} - {title_clean}"

    document = Document(
        id=doc_id,
        filename=file.filename,
        path=saved_path,
        book_id=book.id,
        chapter_number=int(chapter_number),
        chapter_title=title_clean,
        display_name=readable,
        is_processed=False,
        status="pending",
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    return success_response(
        data=_chapter_payload(document), message=MSG_CHAPTER_UPLOADED
    )


@router.get("/books/{book_id}/chapters")
def list_chapters(book_id: str, db: Session = Depends(get_db)):
    """List the chapter documents that belong to a book."""
    book = _get_book_or_404(db, book_id)
    chapters = sorted(
        book.chapters,
        key=lambda d: (d.chapter_number is None, d.chapter_number or 0),
    )
    return success_response(
        data=[_chapter_payload(d) for d in chapters],
        message=MSG_FETCHED,
    )


@router.get("/books/{book_id}/exams")
def list_book_exams(book_id: str, db: Session = Depends(get_db)):
    """List all generated exams for a given book (newest first)."""
    _get_book_or_404(db, book_id)
    exams = (
        db.query(Exam)
        .filter(Exam.book_id == book_id)
        .order_by(Exam.created_at.desc())
        .all()
    )
    return success_response(
        data=[_exam_payload(e) for e in exams], message=MSG_FETCHED
    )
