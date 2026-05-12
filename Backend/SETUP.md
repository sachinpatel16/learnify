# Learnify Backend — local setup (GitHub)

Step-by-step setup for the FastAPI backend using **Python 3.11**, PostgreSQL, and Alembic migrations.

```mermaid
flowchart LR
  clone[Clone repo]
  venv[Python 3.11 venv]
  pip[pip install deps]
  env[Configure .env]
  pg[PostgreSQL ready]
  alembic[alembic upgrade head]
  run[uvicorn app.main:app]
  ready[GET /ready]
  clone --> venv --> pip --> env --> pg --> alembic --> run --> ready
```

---

## Prerequisites

| Requirement | Notes |
|-------------|--------|
| **Python 3.11** | Use `python --version` → `3.11.x`. Other 3.x versions are not guaranteed. |
| **Git** | To clone the repository. |
| **PostgreSQL** | 14+ recommended. The app uses `psycopg2` against PostgreSQL. |
| **OpenAI API** | `OPENAI_API_KEY` for embeddings and RAG (`OpenAIEmbeddings` in `app/config.py`). |
| **Ollama** (optional but typical) | Chat paths use `ChatOllama` with model **`gpt-oss:120b-cloud`** by default in code—install [Ollama](https://ollama.com/) and pull/run that model (or change the model in code for your environment). |
| **Disk** | Space for `UPLOAD_DIR` (default `uploads`) and `CHROMA_DIR` (default `chroma_db`). |

**Python dependencies** are declared in [`requirements.txt`](requirements.txt). For a fully pinned environment you may use [`dev-requirements.txt`](dev-requirements.txt) instead (slower install).

---

## 1. Clone the repository

```bash
git clone <your-fork-or-upstream-url> learnify
cd learnify/Backend
```

All following commands assume your current working directory is **`Backend`** (the folder that contains `app/`, `alembic/`, and `requirements.txt`).

---

## 2. Create a virtual environment (Python 3.11)

**Linux / macOS**

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
```

**Windows (PowerShell)**

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
```

If `py -3.11` is unavailable, install Python 3.11 from [python.org](https://www.python.org/downloads/) and use the full path to `python.exe` with `-m venv .venv`.

---

## 3. Install dependencies

```bash
pip install -r requirements.txt
```

This installs FastAPI, Uvicorn, SQLAlchemy, Alembic, `psycopg2-binary`, LangChain stack, Chroma-related packages, PDF/unstructured tooling, and tests—see [`requirements.txt`](requirements.txt) for the full pinned list.

**Optional — reproducible dev environment**

```bash
pip install -r dev-requirements.txt
```

---

## 4. PostgreSQL — create database and user

Create a database and user (names are examples; adjust to your policy):

```sql
CREATE USER learnify WITH PASSWORD 'your_secure_password';
CREATE DATABASE learnify OWNER learnify;
```

Your **`DATABASE_URL`** must be a PostgreSQL URL, for example:

```text
postgresql://learnify:your_secure_password@localhost:5432/learnify
```

Ensure the server is running and reachable from the machine where you run the API and Alembic.

---

## 5. Environment variables

Copy the example file and edit values:

**Linux / macOS**

```bash
cp .env_example .env
```

**Windows (PowerShell)**

```powershell
Copy-Item .env_example .env
```

### Required / strongly recommended (from `.env_example` and app usage)

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | PostgreSQL connection string (**required** for `app.database` and Alembic). |
| `SECRET_KEY` | JWT signing; set a long random value in any environment that issues tokens. |
| `OPENAI_API_KEY` | Embeddings and RAG features that call OpenAI. |

### Optional tuning (from `app/config.py`)

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATABASE_POOL_SIZE` | `5` | SQLAlchemy pool size. |
| `DATABASE_MAX_OVERFLOW` | `10` | Extra connections beyond pool size. |
| `DATABASE_POOL_RECYCLE` | `280` | Recycle connections (seconds). |
| `ALLOWED_ORIGINS` | `*` | CORS: comma-separated origins, or `*` for permissive dev. |
| `RAG_QUERY_MAX_WORKERS` | `8` | Parallel RAG query workers. |
| `CHAT_MAX_TOKENS` | `1000` | Chat generation cap. |
| `EMBEDDING_MODEL` | `text-embedding-ada-002` | OpenAI embedding model name. |
| `EXAM_GEN_MAX_WORKERS` | `4` | Parallel exam generation workers. |
| `EXAM_CHAPTER_CACHE_TTL_SECONDS` | `300` | Chapter cache TTL. |
| `EXAM_CHAPTER_CACHE_MAX_ITEMS` | `64` | Chapter cache size. |
| `UPLOAD_DIR` | `uploads` | Uploaded files (must be writable; checked on `/ready`). |
| `CHROMA_DIR` | `chroma_db` | Chroma persistence (must be writable; checked on `/ready`). |

`python-dotenv` loads `.env` when the app and Alembic `env.py` import `app.config`.

---

## 6. Database migrations (Alembic)

Run these from the **`Backend`** directory with **`DATABASE_URL`** set (via `.env` in the shell session, or export it explicitly).

**Linux / macOS**

```bash
export $(grep -v '^#' .env | xargs)   # optional: load .env into shell
alembic current                        # optional: show current revision
alembic history                        # optional: list migration chain
alembic upgrade head                   # apply all pending migrations
```

**Windows (PowerShell)** — if Alembic does not auto-load `.env`, set the URL for the session:

```powershell
$env:DATABASE_URL = "postgresql://learnify:your_secure_password@localhost:5432/learnify"
alembic current
alembic upgrade head
```

### Revision summary (as shipped in this repo)

| Revision | File | Description |
|----------|------|-------------|
| **0001** | `alembic/versions/0001_test.py` | Initial schema: `books`, `subjects`, `documents`, `exams`, and related tables. |
| **0002** | `alembic/versions/0002_add_new_files_field.py` | Adds nullable `title` column on `exams`. |

`alembic upgrade head` applies **0001** then **0002** in order.

### Alembic vs application startup

On startup, `app/main.py` also runs **`Base.metadata.create_all()`** for convenience in development. For **teams and production**, treat **Alembic** as the source of truth: always run `alembic upgrade head` after pulling changes. Relying only on `create_all` can hide migration drift.

---

## 7. Run the API

From **`Backend`**:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- **`--reload`** is for development only.
- The import path is **`app.main:app`** because the package root is the `Backend` folder.

API routes are mounted under **`/rag`** for books and exams (see `app/routes/*`). Interactive docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

---

## 8. Smoke checks

| Endpoint | Purpose |
|----------|---------|
| `GET http://127.0.0.1:8000/health` | Liveness; no database call. |
| `GET http://127.0.0.1:8000/ready` | Readiness: PostgreSQL ping and writable **`UPLOAD_DIR`** / **`CHROMA_DIR`**. Returns **503** if a check fails. |

Example:

```bash
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/ready
```

---

## Troubleshooting

| Symptom | What to check |
|---------|----------------|
| `DATABASE_URL` / connection errors on import or Alembic | `.env` present in `Backend`, URL correct, PostgreSQL running, firewall, credentials. |
| **`/ready`** returns **503** | Database reachable; directories for `UPLOAD_DIR` and `CHROMA_DIR` exist and are writable by the process user. |
| **`ModuleNotFoundError: langchain_ollama`** | Run `pip install -r requirements.txt` again (includes `langchain-ollama`). If you installed an older tree, `pip install langchain-ollama`. |
| Chat / exam features fail talking to the LLM | Ollama running locally; model available (default in code: **`gpt-oss:120b-cloud`**). |
| OpenAI errors | `OPENAI_API_KEY` set; billing and model access for `EMBEDDING_MODEL`. |
| Alembic “Target database is not up to date” | Pull latest code, then `alembic upgrade head`. |

---

## Quick reference — dependency categories

- **Web**: FastAPI, Uvicorn, Starlette, `python-multipart`
- **Database**: SQLAlchemy, Alembic, `psycopg2-binary`, greenlet
- **Auth / crypto**: passlib, bcrypt, python-jose, cryptography, PyJWT
- **Validation / settings**: Pydantic, pydantic-settings, email-validator
- **HTTP**: requests, httpx
- **RAG / ML**: LangChain packages, langchain-openai, langchain-chroma, langchain-ollama, PyMuPDF, unstructured, docx2txt, bs4
- **Testing**: pytest

For exact versions, open [`requirements.txt`](requirements.txt).
