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

## API surface

The FastAPI app exposes:

- **`GET /health`** — Liveness (no database call).
- **`GET /ready`** — Readiness: database ping and checks that configured `UPLOAD_DIR` and `CHROMA_DIR` are writable (returns `503` if a path is missing or not writable).

**`/rag/*` routes** (same envelope as above) are mounted from two routers in `app/main.py`:

- **Books / subjects / chapters** — `book_routes`: books, chapter upload and processing, per-book exam list, subjects CRUD.
- **Exams** — `exam_routes`: generate exams, poll status (`GET /rag/exams/{exam_id}`), **long-poll** while pending/generating (`GET /rag/exams/{exam_id}/wait`), student paper, answer key.

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
  "message": "Book fetched successfully",
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

### `POST /rag/books/{book_id}/chapters/{chapter_id}/process`
Process an uploaded chapter (enqueue embedding into the vector store for exam generation). Processing runs in the background; poll `GET /rag/books/{book_id}/chapters` or `GET /rag/books/{book_id}` for `is_processed` / `status`.

**Params**
- `book_id` (path)
- `chapter_id` (path)

**Response (202)**
```json
{
  "success": true,
  "message": "Chapter processing started",
  "data": {
    "id": "doc_id_5",
    "book_id": "book_id",
    "chapter_number": 5,
    "chapter_title": "Light - Reflection and Refraction",
    "status": "processing",
    "is_processed": false,
    "vector_namespace": null
  }
}
```

**Error examples**
- `404` book/chapter not found
- `400` processing validation error
- `500` processing failed

---

### `GET /rag/books/{book_id}/exams`
List generated exams for the book (newest first). Each item is a full exam record: `id`, `book_id`, `title`, `spec`, `paper` (when completed), `total_marks`, `status`, `error_message`, `created_at`, `updated_at`.

**Response (200)**
```json
{
  "success": true,
  "message": "Data fetched successfully",
  "data": [
    {
      "id": "exam_id",
      "book_id": "book_id",
      "title": "Chapter 5 and 6 Unit Test",
      "spec": { },
      "paper": null,
      "total_marks": 0,
      "status": "pending",
      "error_message": null,
      "created_at": "2026-04-29T00:00:00+00:00",
      "updated_at": "2026-04-29T00:00:00+00:00"
    }
  ]
}
```

---

## Exams (student paper + teacher answer-key)

### `POST /rag/exams`
Generate an exam from one Book and multiple chapter numbers.

**`language` (exam output)**

Controls the language of generated questions, MCQ options, short-answer expected answers, and explanations. Stored on the paper and returned on student/teacher views.

| Output language | Accepted values (examples) |
|-----------------|----------------------------|
| English (default) | `English`, `english`, `en` |
| Gujarati | `Gujarati`, `gujarati`, `gu` |
| Hindi | `Hindi`, `hindi`, `hi` |

Names are matched case-insensitively; short aliases normalize to the canonical names **English**, **Gujarati**, and **Hindi**. Hindi prompts request Devanagari script; Gujarati prompts request Gujarati script.

Omit `language` to default to English. Unsupported values return **`422` Validation error** with a message such as: `Unsupported exam output language 'fr'. Use English, Gujarati, or Hindi (aliases: en, gu, hi).`

**Body (JSON)**
```json
{
  "book_id": "book_id",
  "title": "Chapter 5 and 6 Unit Test",
  "chapters": [5, 6],
  "sections": [
    { "type": "mcq", "count": 10, "marks_each": 1 },
    { "type": "short_answer", "count": 5, "marks_each": 2 }
  ],
  "difficulty": "medium",
  "language": "English",
  "standard": "10",
  "subject": "Science",
  "per_chapter_distribution": "proportional"
}
```

For the same paper in Hindi or Gujarati, set `"language": "hi"` or `"language": "Gujarati"` (or `en` / `gu`).

**Response (202)** — returns a full exam row (generation runs in the background). Clients should track `status` with **`GET /rag/exams/{exam_id}/wait`** (long-poll; recommended) or occasional **`GET /rag/exams/{exam_id}`** until `completed` or `failed`, then call the paper/answer-key endpoints.

```json
{
  "success": true,
  "message": "Exam generation started",
  "data": {
    "id": "exam_id",
    "book_id": "book_id",
    "title": "Chapter 5 and 6 Unit Test",
    "spec": { },
    "paper": null,
    "total_marks": 0,
    "status": "pending",
    "error_message": null,
    "created_at": "2026-04-29T00:00:00+00:00",
    "updated_at": "2026-04-29T00:00:00+00:00"
  }
}
```

**Error examples**
- `404` book not found
- `400` chapters missing from the book
```json
{ "success": false, "message": "Chapters not found in this book: [99]", "data": null }
```
- `400` chapters not yet processed
```json
{ "success": false, "message": "Chapters not yet processed: [6]. Process them before requesting an exam.", "data": null }
```

---

### `GET /rag/exams/{exam_id}`
Get exam status and full stored record (paper included after completion). Use this for a **single** snapshot (refresh, debugging). While generation is in progress, calling it in a tight loop creates unnecessary load; prefer **`GET /rag/exams/{exam_id}/wait`** (long-poll, documented in the next section) for polling.

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

### `GET /rag/exams/{exam_id}/wait`
Long-poll exam status so clients avoid tight `GET /rag/exams/{exam_id}` loops. The handler re-reads the database every `interval` seconds (default **1**, min **0.5**, max **5**) until the exam is no longer `pending` or `generating`, or until `timeout` seconds elapse (default **30**, min **1**, max **45**).

**Example**

```http
GET /rag/exams/7f807882-14d7-41e9-af2a-5d617f2d9161/wait?timeout=38&interval=1
```

**Query parameters**

| Name | Default | Range | Meaning |
|------|---------|-------|---------|
| `timeout` | 30 | 1–45 | Maximum seconds to keep the request open. |
| `interval` | 1 | 0.5–5 | Sleep between DB checks while still pending/generating. |

**Response (200) — terminal status (`completed` or `failed`)**

Same `data` shape as `GET /rag/exams/{exam_id}`; `message` is `Exam fetched successfully`.

**Response (200) — still `pending` or `generating` after `timeout`**

Same `data` shape as above (current row); `message` is `Exam generation still in progress`. The client should call this endpoint again (or use `GET /rag/exams/{exam_id}`) until status settles.

**Error**

- `404` exam not found

---

### `DELETE /rag/exams/{exam_id}`
Delete an exam by id (works for pending/generating/completed/failed records).

**Response (200)**
```json
{
  "success": true,
  "message": "Exam deleted successfully",
  "data": null
}
```

**Error**
- `404` exam not found

---

### `GET /rag/exams/{exam_id}/paper`
Student-facing exam paper view (no answers/explanations leaked). Only available when the exam status is **`completed`** and a `paper` exists.

**Response (200)**
```json
{
  "success": true,
  "message": "Paper fetched successfully",
  "data": {
    "exam_id": "exam_id",
    "book": { "id": "book_id", "title": "Class 10 Science NCERT" },
    "total_marks": 20,
    "difficulty": "medium",
    "language": "English",
    "sections": [
      {
        "title": "Section: MCQ (10 x 1 marks = 10 marks)",
        "type": "mcq",
        "marks_each": 1,
        "questions": [
          {
            "q_no": 1,
            "type": "mcq",
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
- `409` exam not finished yet (e.g. still `pending` or `generating`)
```json
{ "success": false, "message": "Exam is 'generating', not yet completed.", "data": null }
```

---

### `GET /rag/exams/{exam_id}/answer-key`
Teacher-facing answer key (correct options, expected short answers, explanations). Same completion requirement as the paper endpoint.

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

**Error**
- `409` exam not finished yet
```json
{ "success": false, "message": "Exam is 'pending', not yet completed.", "data": null }
```

---

## Subjects

### `GET /rag/subjects`
List all managed subjects.

### `POST /rag/subjects`
Create a subject.

**Body (JSON)**
```json
{
  "name": "Maths",
  "standard": "10",
  "board": "NCERT",
  "language": "en"
}
```

### `PATCH /rag/subjects/{subject_id}`
Update an existing subject.

### `DELETE /rag/subjects/{subject_id}`
Delete a subject. Fails if any book’s subject name matches this subject (case-insensitive).

**Error**
- `409` subject has linked books
```json
{ "success": false, "message": "Cannot delete subject. 3 book(s) are linked to it.", "data": null }
```

