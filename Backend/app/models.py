import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.config import now_utc
from app.database import Base


class Book(Base):
    """A textbook (e.g. 'Class 10 Science NCERT') that owns chapter Documents."""

    __tablename__ = "books"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String, nullable=False)
    standard = Column(String, nullable=True)
    subject = Column(String, nullable=True)
    board = Column(String, nullable=True)
    language = Column(String, nullable=True, default="en")

    created_at = Column(DateTime, default=now_utc, nullable=False)
    updated_at = Column(DateTime, default=now_utc, onupdate=now_utc, nullable=False)

    chapters = relationship(
        "Document",
        back_populates="book",
        cascade="all, delete-orphan",
        order_by="Document.chapter_number",
    )
    exams = relationship(
        "Exam",
        back_populates="book",
        cascade="all, delete-orphan",
    )


class Document(Base):
    """An uploaded document.

    Two flavours:
    - Chapter document: ``book_id`` and ``chapter_number`` are set; chunks
      are tagged with that chapter number for exam generation.
    - Loose document: ``book_id`` is null; treated as a free-form RAG file
      for the legacy ``/rag/query`` endpoint.
    """

    __tablename__ = "documents"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    filename = Column(String, nullable=False)
    path = Column(String, nullable=False)

    # Chapter-document fields (null for loose uploads).
    book_id = Column(
        String,
        ForeignKey("books.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    chapter_number = Column(Integer, nullable=True)
    chapter_title = Column(String, nullable=True)
    display_name = Column(String, nullable=True)

    # Legacy fields - kept for backward compatibility with loose uploads.
    standard = Column(String, nullable=True)
    subject = Column(String, nullable=True)

    # RAG pipeline fields
    is_processed = Column(Boolean, default=False, nullable=False)
    vector_namespace = Column(String, nullable=True)
    status = Column(String, default="pending", nullable=False)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime, default=now_utc, nullable=False)
    updated_at = Column(DateTime, default=now_utc, onupdate=now_utc, nullable=False)

    book = relationship("Book", back_populates="chapters")

    __table_args__ = (
        Index("ix_documents_book_chapter", "book_id", "chapter_number"),
    )


class Exam(Base):
    """A generated exam paper drawn from one or more chapters of a Book."""

    __tablename__ = "exams"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    book_id = Column(
        String,
        ForeignKey("books.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    spec = Column(JSONB, nullable=False)
    paper = Column(JSONB, nullable=True)

    total_marks = Column(Integer, nullable=False, default=0)

    status = Column(String, default="pending", nullable=False)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime, default=now_utc, nullable=False)
    updated_at = Column(DateTime, default=now_utc, onupdate=now_utc, nullable=False)

    book = relationship("Book", back_populates="exams")
