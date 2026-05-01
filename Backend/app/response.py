"""Standard API response envelope: { "success", "message", "data" }.

Use ``success_response()`` in route handlers; errors are formatted by the
global exception handlers in ``app.main`` using the same envelope shape.
"""

from typing import Any, Optional

from pydantic import BaseModel


class APIResponse(BaseModel):
    """Standard envelope for all API responses (success and error)."""

    success: bool
    message: str
    data: Optional[Any] = None


# Generic message constants
MSG_FETCHED = "Data fetched successfully"
MSG_CREATED = "Resource created successfully"
MSG_UPDATED = "Resource updated successfully"
MSG_DELETED = "Resource deleted successfully"
MSG_NOT_FOUND = "Resource not found"
MSG_INTERNAL_ERROR = "Internal server error"

# RAG-specific message constants
MSG_DOC_UPLOADED = "Document uploaded successfully"
MSG_DOC_PROCESSED = "Document processed successfully"
MSG_DOC_DELETED = "Document deleted successfully"
MSG_QUERY_SUCCESS = "Query processed successfully"

# Book-specific message constants
MSG_BOOK_CREATED = "Book created successfully"
MSG_BOOK_FETCHED = "Book fetched successfully"
MSG_BOOK_DELETED = "Book deleted successfully"
MSG_CHAPTER_UPLOADED = "Chapter uploaded successfully"
MSG_CHAPTER_PROCESS_STARTED = "Chapter processing started"
MSG_CHAPTERS_FETCHED = "Chapters fetched successfully"

# Exam-specific message constants
MSG_EXAM_CREATED = "Exam generation started"
MSG_EXAM_FETCHED = "Exam fetched successfully"
MSG_EXAM_DELETED = "Exam deleted successfully"
MSG_PAPER_FETCHED = "Paper fetched successfully"
MSG_ANSWER_KEY_FETCHED = "Answer key fetched successfully"


def success_response(data: Any = None, message: str = MSG_FETCHED) -> dict:
    """Build a standard success envelope dict suitable for FastAPI JSON responses."""
    return {"success": True, "message": message, "data": data}
