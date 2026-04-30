"""HTTP API for the exam-paper generator (book-based, multi-chapter)."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.logger import get_logger
from app.models import Book, Document, Exam
from app.response import (
    MSG_ANSWER_KEY_FETCHED,
    MSG_EXAM_CREATED,
    MSG_EXAM_DELETED,
    MSG_EXAM_FETCHED,
    MSG_PAPER_FETCHED,
    success_response,
)
from app.schemas import (
    AnswerEntry,
    ExamAnswerKey,
    ExamPaperView,
    ExamResponse,
    ExamSpec,
    PaperQuestion,
    PaperSection,
)
from app.services.exam_generator import get_exam_generator

logger = get_logger(__name__)


router = APIRouter(prefix="/rag", tags=["Exams"])


# ── Helpers ──────────────────────────────────────────────────────────────────


def _exam_payload(exam: Exam) -> dict:
    return ExamResponse.model_validate(exam).model_dump(mode="json")


def _build_chapter_snapshots(book: Book, chapter_numbers: list[int]) -> list[dict]:
    """Return ``[{document_id, chapter_number, chapter_title, vector_namespace}, ...]``.

    Validates that every requested chapter has a processed Document; raises
    ``HTTPException`` describing what's missing.
    """
    by_number: dict[int, Document] = {}
    for d in book.chapters:
        if d.chapter_number is not None:
            by_number[int(d.chapter_number)] = d

    missing: list[int] = []
    unprocessed: list[int] = []
    snapshots: list[dict] = []
    for n in chapter_numbers:
        doc = by_number.get(int(n))
        if doc is None:
            missing.append(int(n))
            continue
        if not doc.is_processed or not doc.vector_namespace:
            unprocessed.append(int(n))
            continue
        snapshots.append(
            {
                "document_id": doc.id,
                "chapter_number": int(doc.chapter_number),
                "chapter_title": doc.chapter_title or f"Chapter {doc.chapter_number}",
                "vector_namespace": doc.vector_namespace,
            }
        )

    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Chapters not found in this book: {sorted(missing)}",
        )
    if unprocessed:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Chapters not yet processed: {sorted(unprocessed)}. "
                "Process them before requesting an exam."
            ),
        )
    return snapshots


def _book_snapshot(book: Book) -> dict:
    return {
        "id": book.id,
        "title": book.title,
        "standard": book.standard,
        "subject": book.subject,
        "board": book.board,
        "language": book.language,
    }


# ── Create / poll endpoints ──────────────────────────────────────────────────


@router.post("/exams", status_code=status.HTTP_202_ACCEPTED)
def create_exam(
    spec: ExamSpec,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Schedule an exam-generation job and return ``exam_id`` immediately."""
    book = db.query(Book).filter(Book.id == spec.book_id).first()
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")

    chapter_snapshots = _build_chapter_snapshots(book, spec.chapters)

    exam = Exam(
        book_id=book.id,
        title=spec.title.strip(),
        spec=spec.model_dump(mode="json"),
        paper=None,
        total_marks=0,
        status="pending",
    )
    db.add(exam)
    db.commit()
    db.refresh(exam)

    snapshot = {
        "book": _book_snapshot(book),
        "chapters": chapter_snapshots,
    }
    background_tasks.add_task(_run_exam_generation, exam.id, snapshot)

    return success_response(data=_exam_payload(exam), message=MSG_EXAM_CREATED)


@router.get("/exams/{exam_id}")
def get_exam(exam_id: str, db: Session = Depends(get_db)):
    """Poll the current state of an exam (status + paper if completed)."""
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if exam is None:
        raise HTTPException(status_code=404, detail="Exam not found")
    return success_response(data=_exam_payload(exam), message=MSG_EXAM_FETCHED)


@router.delete("/exams/{exam_id}")
def delete_exam(exam_id: str, db: Session = Depends(get_db)):
    """Delete an exam row by id regardless of status."""
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if exam is None:
        raise HTTPException(status_code=404, detail="Exam not found")

    db.delete(exam)
    db.commit()
    return success_response(data=None, message=MSG_EXAM_DELETED)


# ── Paper / answer-key views ─────────────────────────────────────────────────


@router.get("/exams/{exam_id}/paper")
def get_paper(exam_id: str, db: Session = Depends(get_db)):
    """Student-facing paper view (no answers, no explanations)."""
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if exam is None:
        raise HTTPException(status_code=404, detail="Exam not found")
    if exam.status != "completed" or not exam.paper:
        raise HTTPException(
            status_code=409,
            detail=f"Exam is '{exam.status}', not yet completed.",
        )

    paper: dict[str, Any] = exam.paper
    book = exam.book
    sections: list[PaperSection] = []
    for sec in paper.get("sections", []):
        questions: list[PaperQuestion] = []
        for q in sec.get("questions", []):
            questions.append(
                PaperQuestion(
                    q_no=int(q.get("q_no", 0)),
                    type=sec.get("type"),
                    chapter_number=q.get("chapter_number"),
                    chapter_title=q.get("chapter_title"),
                    question=str(q.get("question", "")),
                    options=q.get("options") if sec.get("type") == "mcq" else None,
                    marks=int(q.get("marks", sec.get("marks_each", 1))),
                )
            )
        sections.append(
            PaperSection(
                title=str(sec.get("title", "")),
                type=sec.get("type"),
                marks_each=int(sec.get("marks_each", 1)),
                questions=questions,
            )
        )

    view = ExamPaperView(
        exam_id=exam.id,
        book={"id": book.id, "title": book.title} if book else {},
        total_marks=int(paper.get("total_marks", exam.total_marks or 0)),
        difficulty=paper.get("difficulty"),
        language=paper.get("language"),
        sections=sections,
    )
    return success_response(data=view.model_dump(mode="json"), message=MSG_PAPER_FETCHED)


@router.get("/exams/{exam_id}/answer-key")
def get_answer_key(exam_id: str, db: Session = Depends(get_db)):
    """Teacher-facing answer key (correct options + expected answers + explanations)."""
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if exam is None:
        raise HTTPException(status_code=404, detail="Exam not found")
    if exam.status != "completed" or not exam.paper:
        raise HTTPException(
            status_code=409,
            detail=f"Exam is '{exam.status}', not yet completed.",
        )

    paper: dict[str, Any] = exam.paper
    answers: list[AnswerEntry] = []
    for sec in paper.get("sections", []):
        sec_type = sec.get("type")
        for q in sec.get("questions", []):
            entry = AnswerEntry(
                q_no=int(q.get("q_no", 0)),
                type=sec_type,
                chapter_number=q.get("chapter_number"),
                marks=int(q.get("marks", sec.get("marks_each", 1))),
            )
            if sec_type == "mcq":
                idx = q.get("correct_index")
                opts = q.get("options") or []
                entry.correct_index = int(idx) if isinstance(idx, int) else None
                if entry.correct_index is not None and 0 <= entry.correct_index < len(opts):
                    entry.correct_option = str(opts[entry.correct_index])
                entry.explanation = q.get("explanation") or None
            else:
                entry.expected_answer = q.get("expected_answer") or None
            answers.append(entry)

    key = ExamAnswerKey(
        exam_id=exam.id,
        total_marks=int(paper.get("total_marks", exam.total_marks or 0)),
        answers=answers,
    )
    return success_response(
        data=key.model_dump(mode="json"), message=MSG_ANSWER_KEY_FETCHED
    )


# ── Background worker ────────────────────────────────────────────────────────


def _run_exam_generation(exam_id: str, snapshot: dict) -> None:
    """Background worker: run the LangGraph pipeline and update the Exam row."""
    db: Optional[Session] = None
    try:
        db = SessionLocal()
        exam = db.query(Exam).filter(Exam.id == exam_id).first()
        if exam is None:
            logger.error(f"Exam {exam_id} disappeared before generation could start")
            return

        exam.status = "generating"
        exam.error_message = None
        db.commit()

        try:
            spec = ExamSpec.model_validate(exam.spec)
        except Exception as e:
            logger.error(f"Stored spec for exam {exam_id} is invalid: {e}")
            exam.status = "failed"
            exam.error_message = f"Invalid spec: {e}"
            db.commit()
            return

        try:
            result = get_exam_generator().run(spec, snapshot)
        except Exception as e:
            logger.exception(f"Exam {exam_id} generation failed")
            exam.status = "failed"
            exam.error_message = str(e)
            db.commit()
            return

        paper = result.get("paper") or {}
        sections = paper.get("sections") or []
        requested_total_questions = sum(int(s.count) for s in spec.sections)
        generated_total_questions = sum(len(s.get("questions") or []) for s in sections)
        requested_total_marks = sum(int(s.count) * int(s.marks_each) for s in spec.sections)
        generated_total_marks = int(result.get("total_marks", 0))
        if (
            generated_total_questions != requested_total_questions
            or generated_total_marks != requested_total_marks
        ):
            exam.status = "failed"
            exam.error_message = (
                "Generated exam does not match requested counts/marks. "
                f"Requested questions={requested_total_questions}, generated={generated_total_questions}; "
                f"requested marks={requested_total_marks}, generated={generated_total_marks}."
            )
            db.commit()
            return

        exam.paper = result["paper"]
        exam.total_marks = generated_total_marks
        exam.status = "completed"
        exam.error_message = None
        db.commit()
        logger.info(f"Exam {exam_id} completed (total_marks={exam.total_marks})")
    except Exception as e:
        logger.exception(f"Unhandled error in exam worker for {exam_id}: {e}")
        if db is not None:
            try:
                exam = db.query(Exam).filter(Exam.id == exam_id).first()
                if exam is not None:
                    exam.status = "failed"
                    exam.error_message = f"Internal error: {e}"
                    db.commit()
            except Exception:
                pass
    finally:
        if db is not None:
            db.close()
