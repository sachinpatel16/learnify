"""HTTP API for Books and per-chapter document uploads."""

from __future__ import annotations

import os
import uuid
from typing import Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    Query,
    status,
)
from starlette.concurrency import run_in_threadpool
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import UPLOAD_DIR
from app.database import SessionLocal, get_db
from app.logger import get_logger
from app.models import Book, Document, Exam, Subject
from app.response import (
    MSG_CREATED,
    MSG_DELETED,
    MSG_UPDATED,
    MSG_BOOK_CREATED,
    MSG_BOOK_DELETED,
    MSG_BOOK_FETCHED,
    MSG_CHAPTER_PROCESS_STARTED,
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
    SubjectCreate,
    SubjectResponse,
    SubjectUpdate,
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


def _subject_payload(subject: Subject) -> dict:
    return SubjectResponse.model_validate(subject).model_dump(mode="json")


def _get_book_or_404(db: Session, book_id: str) -> Book:
    book = db.query(Book).filter(Book.id == book_id).first()
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    return book


def _get_subject_or_404(db: Session, subject_id: str) -> Subject:
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    if subject is None:
        raise HTTPException(status_code=404, detail="Subject not found")
    return subject


def _persist_chapter_upload(
    book_id: str,
    filename: str,
    ext: str,
    contents: bytes,
    chapter_number: int,
    chapter_title: str,
    display_name_optional: Optional[str],
) -> dict:
    """DB + filesystem work for chapter upload (runs in a worker thread)."""
    db = SessionLocal()
    try:
        book = db.query(Book).filter(Book.id == book_id).first()
        if book is None:
            raise HTTPException(status_code=404, detail="Book not found")

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
            with open(saved_path, "wb") as out:
                out.write(contents)
        except Exception as e:
            logger.error("Failed to save uploaded file '%s': %s", filename, e)
            raise HTTPException(status_code=500, detail="Failed to save uploaded file") from e

        title_clean = chapter_title.strip()
        readable = (
            (display_name_optional or "").strip() or f"Chapter {chapter_number} - {title_clean}"
        )

        document = Document(
            id=doc_id,
            filename=filename,
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
        return _chapter_payload(document)
    finally:
        db.close()


def _run_book_chapter_process(book_id: str, chapter_id: str) -> None:
    from app.utils import rag_pipeline

    db = SessionLocal()
    try:
        book = db.query(Book).filter(Book.id == book_id).first()
        if book is None:
            logger.error("Book %s missing before chapter embedding", book_id)
            return
        chapter = (
            db.query(Document)
            .filter(Document.id == chapter_id, Document.book_id == book.id)
            .first()
        )
        if chapter is None:
            logger.error("Chapter %s missing before embedding", chapter_id)
            return

        try:
            namespace = rag_pipeline.process(
                filepath=chapter.path,
                doc_id=chapter.id,
                chapter_number=chapter.chapter_number,
                chapter_title=chapter.chapter_title,
            )
        except FileNotFoundError as e:
            chapter.status = "failed"
            chapter.error_message = str(e)
            db.commit()
            return
        except ValueError as e:
            chapter.status = "failed"
            chapter.error_message = str(e)
            db.commit()
            return
        except Exception as e:
            logger.exception("Failed to process chapter %s", chapter_id)
            chapter.status = "failed"
            chapter.error_message = str(e)
            db.commit()
            return

        chapter.vector_namespace = namespace
        chapter.is_processed = True
        chapter.status = "completed"
        chapter.error_message = None
        db.commit()
    finally:
        db.close()


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
def list_books(
    subject: Optional[str] = Query(default=None, min_length=1),
    db: Session = Depends(get_db),
):
    """List all books (newest first)."""
    query = db.query(Book)
    if subject:
        subject_value = subject.strip()
        matched_subject = (
            db.query(Subject).filter(func.lower(Subject.id) == subject_value.lower()).first()
        )
        if matched_subject is not None:
            subject_value = matched_subject.name
        query = query.filter(func.lower(Book.subject) == subject_value.lower())
    books = query.order_by(Book.created_at.desc()).all()
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
):
    """Upload one chapter PDF (or other supported file) to a book.

    The user supplies ``chapter_number`` and ``chapter_title``; we never
    auto-detect. A readable ``display_name`` like 'Chapter 5 - Light' is
    auto-built when the caller doesn't provide one.
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

    contents = await file.read()
    payload = await run_in_threadpool(
        _persist_chapter_upload,
        book_id,
        file.filename,
        ext,
        contents,
        chapter_number,
        chapter_title,
        display_name,
    )
    return success_response(data=payload, message=MSG_CHAPTER_UPLOADED)


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


@router.post(
    "/books/{book_id}/chapters/{chapter_id}/process",
    status_code=status.HTTP_202_ACCEPTED,
)
def process_book_chapter(
    book_id: str,
    chapter_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Enqueue embedding for a chapter; poll the book or chapter list for status."""
    book = _get_book_or_404(db, book_id)
    chapter = (
        db.query(Document)
        .filter(Document.id == chapter_id, Document.book_id == book.id)
        .first()
    )
    if chapter is None:
        raise HTTPException(status_code=404, detail="Chapter not found for this book")

    chapter.status = "processing"
    chapter.error_message = None
    db.commit()
    db.refresh(chapter)

    background_tasks.add_task(_run_book_chapter_process, book_id, chapter_id)

    return success_response(
        data=_chapter_payload(chapter), message=MSG_CHAPTER_PROCESS_STARTED
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


# ── Subject endpoints ────────────────────────────────────────────────────────


@router.get("/subjects")
def list_subjects(db: Session = Depends(get_db)):
    subjects = db.query(Subject).order_by(Subject.name.asc()).all()
    return success_response(data=[_subject_payload(s) for s in subjects], message=MSG_FETCHED)


@router.post("/subjects", status_code=status.HTTP_201_CREATED)
def create_subject(payload: SubjectCreate, db: Session = Depends(get_db)):
    name = payload.name.strip()
    existing = db.query(Subject).filter(func.lower(Subject.name) == name.lower()).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Subject already exists")

    subject = Subject(
        name=name,
        standard=payload.standard.strip() if payload.standard else None,
        board=payload.board.strip() if payload.board else None,
        language=(payload.language or "en").strip() or "en",
    )
    db.add(subject)
    db.commit()
    db.refresh(subject)
    return success_response(data=_subject_payload(subject), message=MSG_CREATED)


@router.patch("/subjects/{subject_id}")
def update_subject(subject_id: str, payload: SubjectUpdate, db: Session = Depends(get_db)):
    subject = _get_subject_or_404(db, subject_id)
    old_name = subject.name

    if payload.name is not None:
        new_name = payload.name.strip()
        existing = (
            db.query(Subject)
            .filter(func.lower(Subject.name) == new_name.lower(), Subject.id != subject.id)
            .first()
        )
        if existing is not None:
            raise HTTPException(status_code=409, detail="Subject already exists")
        subject.name = new_name

    if payload.standard is not None:
        subject.standard = payload.standard.strip() or None
    if payload.board is not None:
        subject.board = payload.board.strip() or None
    if payload.language is not None:
        subject.language = payload.language.strip() or None

    db.commit()

    # Keep book subject labels aligned with managed subject rename.
    if payload.name is not None and old_name != subject.name:
        db.query(Book).filter(func.lower(Book.subject) == old_name.lower()).update(
            {"subject": subject.name},
            synchronize_session=False,
        )
        db.commit()

    db.refresh(subject)
    return success_response(data=_subject_payload(subject), message=MSG_UPDATED)


@router.delete("/subjects/{subject_id}")
def delete_subject(subject_id: str, db: Session = Depends(get_db)):
    subject = _get_subject_or_404(db, subject_id)
    linked_books = (
        db.query(Book.id).filter(func.lower(Book.subject) == subject.name.lower()).count()
    )
    if linked_books > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete subject. {linked_books} book(s) are linked to it.",
        )

    db.delete(subject)
    db.commit()
    return success_response(data=None, message=MSG_DELETED)
