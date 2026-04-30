# Book RAG Logic and APIs

## 1) Create Book

- Purpose: create a book container where chapters and exams are attached.
- API: `POST /rag/books`
- Input:
  - `title` (required)
  - `standard`, `subject`, `board`, `language` (optional)
- Logic:
  - Validates payload with `BookCreate`.
  - Trims string fields.
  - Inserts a new `Book` row.
  - Returns book metadata.

## 2) Upload Chapters to Book

- Purpose: attach chapter files to the created book.
- API: `POST /rag/books/{book_id}/chapters`
- Form-data input:
  - `file` (required)
  - `chapter_number` (required, >= 1)
  - `chapter_title` (required)
  - `display_name` (optional)
- Logic:
  - Validates `book_id` exists.
  - Validates file extension against supported types.
  - Prevents duplicate chapter number for same book.
  - Stores file in upload directory.
  - Creates `Document` row with status `pending`.

## 3) Process Chapter into Vector Store (RAG Indexing)

- Purpose: convert chapter document into embeddings for retrieval.
- API: `POST /rag/books/{book_id}/chapters/{chapter_id}/process`
- Logic:
  - Validates book + chapter relation.
  - Sets chapter status to `processing`.
  - Calls `rag_pipeline.process(...)` with:
    - file path
    - document id
    - chapter number/title
  - On success:
    - saves `vector_namespace`
    - marks `is_processed = true`
    - sets status `completed`
  - On failure: sets status `failed` with error message.

## 4) Generate Exam (Async)

- Purpose: create an exam from selected processed chapters.
- API: `POST /rag/exams`
- Input (`ExamSpec`):
  - `book_id`
  - `title`
  - `chapters` (list of chapter numbers)
  - `sections` (question type/count/marks)
  - `difficulty`, `language`, optional metadata
  - `per_chapter_distribution`
- Logic:
  - Validates book exists.
  - Validates all requested chapters:
    - must exist in that book
    - must already be processed and have `vector_namespace`
  - Creates `Exam` row with status `pending`.
  - Adds background task `_run_exam_generation(exam_id, snapshot)`.
  - Returns immediately (`202 Accepted` style behavior).

## 5) Background Exam Generation Worker

- Internal flow: `_run_exam_generation(exam_id, snapshot)`
- Logic:
  - Sets exam status `generating`.
  - Rebuilds/validates `ExamSpec` from stored spec.
  - Calls `get_exam_generator().run(spec, snapshot)`.
  - On success:
    - stores generated `paper`
    - computes/stores `total_marks`
    - sets status `completed`
  - On failure:
    - sets status `failed`
    - stores error message.

## 6) Poll and Fetch Generated Output

- Poll exam status:
  - `GET /rag/exams/{exam_id}`
  - Returns exam row (`pending` | `generating` | `completed` | `failed`).

- Fetch student paper (only when completed):
  - `GET /rag/exams/{exam_id}/paper`
  - Builds student-safe view (no answers/explanations).

- Fetch teacher answer key (only when completed):
  - `GET /rag/exams/{exam_id}/answer-key`
  - Returns correct options / expected answers and explanations.

## 7) Book-Level Listing APIs Used in Flow

- List books: `GET /rag/books`
- Get one book with chapters: `GET /rag/books/{book_id}`
- List book chapters: `GET /rag/books/{book_id}/chapters`
- List exams by book: `GET /rag/books/{book_id}/exams`
