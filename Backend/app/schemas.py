from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_serializer


def _utc_iso(dt: datetime | None) -> str | None:
    """Serialize a datetime as an ISO-8601 UTC string (treating naive as UTC)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


# ── Book ─────────────────────────────────────────────────────────────────────


class BookCreate(BaseModel):
    """Body for ``POST /rag/books``."""

    title: str = Field(..., min_length=1)
    standard: Optional[str] = None
    subject: Optional[str] = None
    board: Optional[str] = None
    language: Optional[str] = "en"


class BookResponse(BaseModel):
    """A book row without its chapters."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    standard: Optional[str] = None
    subject: Optional[str] = None
    board: Optional[str] = None
    language: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def _serialize_dt(self, v: datetime | None) -> str | None:
        return _utc_iso(v)


# ── Subject ──────────────────────────────────────────────────────────────────


class SubjectCreate(BaseModel):
    """Body for ``POST /rag/subjects``."""

    name: str = Field(..., min_length=1)
    standard: Optional[str] = None
    board: Optional[str] = None
    language: Optional[str] = "en"


class SubjectUpdate(BaseModel):
    """Body for ``PATCH /rag/subjects/{subject_id}``."""

    name: Optional[str] = Field(default=None, min_length=1)
    standard: Optional[str] = None
    board: Optional[str] = None
    language: Optional[str] = None


class SubjectResponse(BaseModel):
    """A managed subject record."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    standard: Optional[str] = None
    board: Optional[str] = None
    language: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def _serialize_dt(self, v: datetime | None) -> str | None:
        return _utc_iso(v)


# ── Document (chapter or loose) ──────────────────────────────────────────────


class ChapterDocumentResponse(BaseModel):
    """A processed chapter document inside a book."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    book_id: Optional[str] = None
    chapter_number: Optional[int] = None
    chapter_title: Optional[str] = None
    display_name: Optional[str] = None
    filename: str
    status: str
    is_processed: bool
    vector_namespace: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def _serialize_dt(self, v: datetime | None) -> str | None:
        return _utc_iso(v)


class DocumentResponse(ChapterDocumentResponse):
    """Backward-compatible alias used by legacy loose-upload endpoints."""

    pass


class BookWithChapters(BookResponse):
    """A book with its chapter documents nested."""

    chapters: list[ChapterDocumentResponse] = Field(default_factory=list)


# ── Legacy RAG query ─────────────────────────────────────────────────────────


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, description="User question for the RAG pipeline.")
    document_ids: Optional[list[str]] = Field(
        default=None,
        description="Restrict retrieval to these documents. Omit to query all processed documents.",
    )


class QueryResponse(BaseModel):
    answer: str
    context_found: bool
    used_documents: list[str] = Field(default_factory=list)


# ── Exam generation ──────────────────────────────────────────────────────────


QuestionType = Literal["mcq", "short_answer"]
Difficulty = Literal["easy", "medium", "hard"]
ChapterDistribution = Literal["proportional", "evenly_split"]


class ExamSection(BaseModel):
    """One section of the requested paper, e.g. '10 MCQs worth 1 mark each'."""

    type: QuestionType
    count: int = Field(..., ge=1, le=100)
    marks_each: int = Field(..., ge=1, le=20)


class ExamSpec(BaseModel):
    """The request body for ``POST /rag/exams``."""

    book_id: str
    title: str = Field(..., min_length=1, max_length=200)
    chapters: list[int] = Field(
        ...,
        min_length=1,
        description="Chapter numbers to draw questions from.",
    )
    sections: list[ExamSection] = Field(..., min_length=1)
    difficulty: Difficulty = "medium"
    language: str = "en"
    standard: Optional[str] = None
    subject: Optional[str] = None
    per_chapter_distribution: ChapterDistribution = Field(
        default="proportional",
        description=(
            "How to split the question quota across chapters. "
            "'proportional' weights by chapter text length; "
            "'evenly_split' assigns the same count to each chapter."
        ),
    )


class MCQ(BaseModel):
    """A multiple-choice question generated by the LLM."""

    question: str
    options: list[str] = Field(..., min_length=2, max_length=6)
    correct_index: int = Field(..., ge=0)
    explanation: str = ""
    marks: int = Field(default=1, ge=1)


class ShortAnswer(BaseModel):
    """A short-answer question with an expected model answer."""

    question: str
    expected_answer: str
    marks: int = Field(default=2, ge=1)


class GeneratedBatch(BaseModel):
    """Schema returned by the LLM for one section of source text."""

    mcqs: list[MCQ] = Field(default_factory=list)
    short_answers: list[ShortAnswer] = Field(default_factory=list)


class ExamResponse(BaseModel):
    """An exam record returned to the API client."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    book_id: str
    title: Optional[str] = None
    spec: dict[str, Any]
    paper: Optional[dict[str, Any]] = None
    total_marks: int
    status: str
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def _serialize_dt(self, v: datetime | None) -> str | None:
        return _utc_iso(v)


# ── Paper / answer-key views ─────────────────────────────────────────────────


class PaperQuestion(BaseModel):
    """A question as a student sees it: no answers, no explanation."""

    q_no: int
    type: QuestionType
    chapter_number: Optional[int] = None
    chapter_title: Optional[str] = None
    question: str
    options: Optional[list[str]] = None
    marks: int


class PaperSection(BaseModel):
    title: str
    type: QuestionType
    marks_each: int
    questions: list[PaperQuestion] = Field(default_factory=list)


class ExamPaperView(BaseModel):
    """Student-facing view of a completed exam (no answers leaked)."""

    exam_id: str
    book: dict[str, Any]
    total_marks: int
    difficulty: Optional[str] = None
    language: Optional[str] = None
    sections: list[PaperSection] = Field(default_factory=list)


class AnswerEntry(BaseModel):
    q_no: int
    type: QuestionType
    chapter_number: Optional[int] = None
    marks: int
    correct_index: Optional[int] = None
    correct_option: Optional[str] = None
    expected_answer: Optional[str] = None
    explanation: Optional[str] = None


class ExamAnswerKey(BaseModel):
    """Teacher-facing answer key for a completed exam."""

    exam_id: str
    total_marks: int
    answers: list[AnswerEntry] = Field(default_factory=list)
