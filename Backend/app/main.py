from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.database import Base, engine
from app.logger import get_logger
from app.response import MSG_INTERNAL_ERROR
from app.routes import book_routes, exam_routes

logger = get_logger(__name__)


def _error_envelope(message: str, data=None) -> dict:
    return {"success": False, "message": message, "data": data}


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    logger.info("RAG service started.")
    yield
    logger.info("RAG service stopped.")


app = FastAPI(lifespan=lifespan, title="RAG Pipeline API")


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Format HTTPException as the standard envelope."""
    detail = exc.detail
    if isinstance(detail, str):
        message, data = detail, None
    elif isinstance(detail, list):
        message, data = "Validation error", detail
    elif isinstance(detail, dict):
        message, data = "Error", detail
    else:
        message, data = str(detail), None

    return JSONResponse(
        status_code=exc.status_code,
        content=_error_envelope(message=message, data=data),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catch-all: return 500 in standard envelope and log the real error."""
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content=_error_envelope(message=MSG_INTERNAL_ERROR, data=None),
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(book_routes.router)
app.include_router(exam_routes.router)
