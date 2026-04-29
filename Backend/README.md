## Learnify RAG / Exam API

All endpoints use a common response envelope.

### Success response (HTTP 2xx)
```json
{
  "success": true,
  "message": "Data fetched successfully",
  "data": { }
}
```

### Error response (HTTP 4xx/5xx)
```json
{
  "success": false,
  "message": "Internal server error",
  "data": null
}
```

`message` comes from the backend constants / exception handlers, and `data` is usually `null` for server errors.

---

## Books (chapter-based uploads)

### `POST /rag/books`
Create a new book (example: “Class 10 Science NCERT”).

**Body (JSON)**
```json
{
  "title": "Class 10 Science NCERT",
  "standard": "10",
  "subject": "Science",
  "board": "NCERT",
  "language": "en"
}
```

**Response (201)**
```json
{
  "success": true,
  "message": "Book created successfully",
  "data": {
    "id": "book_id",
    "title": "Class 10 Science NCERT",
    "standard": "10",
    "subject": "Science",
    "board": "NCERT",
    "language": "en",
    "created_at": "2026-04-29T00:00:00+00:00",
    "updated_at": "2026-04-29T00:00:00+00:00"
  }
}
```

**Error examples**
- `400/422` (validation): invalid/missing `title`
```json
{ "success": false, "message": "Validation error", "data": [/* details */] }
```
- `500`
```json
{ "success": false, "message": "Internal server error", "data": null }
```

---

### `GET /rag/books`
List all books.

**Response (200)**
```json
{
  "success": true,
  "message": "Data fetched successfully",
  "data": [ { "id": "book_id", "title": "..." } ]
}
```

---

### `GET /rag/books/{book_id}`
Get a book with its uploaded chapters.

**Params**
- `book_id` (path): string

**Response (200)**
```json
{
  "success": true,
  "message": "Data fetched successfully",
  "data": {
    "id": "book_id",
    "title": "Class 10 Science NCERT",
    "chapters": [
      {
        "id": "doc_id",
        "chapter_number": 5,
        "chapter_title": "Light - Reflection and Refraction",
        "display_name": "Chapter 5 - Light - Reflection and Refraction",
        "is_processed": true,
        "vector_namespace": "doc-abc12345"
      }
    ]
  }
}
```

**Error**
- `404`
```json
{ "success": false, "message": "Book not found", "data": null }
```

---

### `DELETE /rag/books/{book_id}`
Delete a book, its chapter documents, and its exams.

**Params**
- `book_id` (path): string

**Response (200)**
```json
{ "success": true, "message": "Book deleted successfully", "data": null }
```

---

### `POST /rag/books/{book_id}/chapters`
Upload one chapter document (one upload = one chapter).

**Params**
- `book_id` (path)

**Body (multipart/form-data)**
- `file` (required): chapter PDF (or supported text format)
- `chapter_number` (required): integer (e.g. `5`)
- `chapter_title` (required): string (readable title)
- `display_name` (optional): string for UI

**Example (curl)**
```bash
curl -X POST http://localhost:8000/rag/books/<book_id>/chapters \
  -F "file=@./chapter5.pdf" \
  -F "chapter_number=5" \
  -F "chapter_title=Light - Reflection and Refraction"
```

**Response (201)**
```json
{
  "success": true,
  "message": "Chapter uploaded successfully",
  "data": {
    "id": "doc_id_5",
    "book_id": "book_id",
    "chapter_number": 5,
    "chapter_title": "Light - Reflection and Refraction",
    "display_name": "Chapter 5 - Light - Reflection and Refraction",
    "status": "pending"
  }
}
```

**Error examples**
- `409` chapter already exists
```json
{ "success": false, "message": "Chapter 5 already exists for this book ...", "data": null }
```
- `400` invalid fields / unsupported file type
```json
{ "success": false, "message": "Unsupported file type '.bin'. Allowed: ...", "data": null }
```

---

### `GET /rag/books/{book_id}/chapters`
List uploaded chapters for the book.

**Response (200)**
```json
{
  "success": true,
  "message": "Data fetched successfully",
  "data": [ { "chapter_number": 5, "is_processed": true }, { "chapter_number": 6, "is_processed": false } ]
}
```

---

### `GET /rag/books/{book_id}/exams`
List generated exams for the book.

**Response (200)**
```json
{
  "success": true,
  "message": "Data fetched successfully",
  "data": [ { "id": "exam_id", "status": "completed" } ]
}
```

---

## Documents (loose upload for Q&A)

These endpoints are for “loose” RAG files (not tied to a book/chapter).

### `POST /rag/documents`
Upload a loose document for Q&A.

**Body (multipart/form-data)**
- `file` (required)

**Response (201)**
```json
{
  "success": true,
  "message": "Document uploaded successfully",
  "data": { "id": "doc_id", "filename": "book.txt", "status": "pending" }
}
```

---

### `POST /rag/documents/{doc_id}/process`
Embed the loose document into Chroma for Q&A.

**Params**
- `doc_id` (path)

**Response (200)**
```json
{
  "success": true,
  "message": "Document processed successfully",
  "data": { "id": "doc_id", "is_processed": true, "vector_namespace": "doc-..." }
}
```

---

### `GET /rag/documents`
List loose documents.

---

### `POST /rag/query`
Ask a question using similarity retrieval over processed loose documents.

**Body (JSON)**
```json
{
  "question": "What is the definition of force?",
  "document_ids": ["doc_id_1", "doc_id_2"]
}
```

**Response (200)**
```json
{
  "success": true,
  "message": "Query processed successfully",
  "data": {
    "answer": " ... ",
    "context_found": true,
    "used_documents": ["doc_id_1"]
  }
}
```

---

### `DELETE /rag/documents/{doc_id}`
Delete a loose document + its Chroma collection + uploaded file.

**Response (200)**
```json
{ "success": true, "message": "Document deleted successfully", "data": null }
```

---

## Exams (student paper + teacher answer-key)

### `POST /rag/exams`
Generate an exam from one Book and multiple chapter numbers.

**Body (JSON)**
```json
{
  "book_id": "book_id",
  "chapters": [5, 6],
  "sections": [
    { "type": "mcq", "count": 10, "marks_each": 1 },
    { "type": "short_answer", "count": 5, "marks_each": 2 }
  ],
  "difficulty": "medium",
  "language": "en",
  "standard": "10",
  "subject": "Science",
  "per_chapter_distribution": "proportional"
}
```

**Response (202)**
```json
{
  "success": true,
  "message": "Exam generation started",
  "data": {
    "id": "exam_id",
    "book_id": "book_id",
    "status": "pending",
    "paper": null
  }
}
```

**Error examples**
- `404` book not found
- `400` chapters not found or not processed yet
```json
{ "success": false, "message": "Chapters not yet processed: [6]. Process them first.", "data": null }
```

---

### `GET /rag/exams/{exam_id}`
Get exam status and full stored record (paper included after completion).

**Response (200)**
```json
{
  "success": true,
  "message": "Exam fetched successfully",
  "data": {
    "id": "exam_id",
    "book_id": "book_id",
    "status": "completed",
    "paper": { "total_marks": 20, "sections": [/* ... */] }
  }
}
```

---

### `GET /rag/exams/{exam_id}/paper`
Student-facing exam paper view (no answers/explanations leaked).

**Response (200)**
```json
{
  "success": true,
  "message": "Paper fetched successfully",
  "data": {
    "exam_id": "exam_id",
    "total_marks": 20,
    "sections": [
      {
        "title": "Section: MCQ (10 x 1 marks = 10 marks)",
        "type": "mcq",
        "marks_each": 1,
        "questions": [
          {
            "q_no": 1,
            "chapter_number": 5,
            "chapter_title": " ... ",
            "question": " ... ",
            "options": ["A", "B", "C", "D"],
            "marks": 1
          }
        ]
      }
    ]
  }
}
```

**Error**
- `409` exam not completed yet
```json
{ "success": false, "message": "Exam is 'generating', not yet completed.", "data": null }
```

---

### `GET /rag/exams/{exam_id}/answer-key`
Teacher-facing answer key view.

**Response (200)**
```json
{
  "success": true,
  "message": "Answer key fetched successfully",
  "data": {
    "exam_id": "exam_id",
    "total_marks": 20,
    "answers": [
      {
        "q_no": 1,
        "type": "mcq",
        "chapter_number": 5,
        "marks": 1,
        "correct_index": 2,
        "correct_option": "C",
        "explanation": " ..."
      }
    ]
  }
}
```

