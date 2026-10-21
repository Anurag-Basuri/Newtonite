"""
Opsboard FastAPI application entry point.
Configures lifespan events, CORS, RFC 7807 Problem Details exception handlers,
and registers all API v1 routes.
"""

from contextlib import asynccontextmanager
import logging
import uuid
from typing import AsyncGenerator
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pymongo.errors import DuplicateKeyError

from app.api import ai, approvals, auth, features, items, notifications, overview, search, stream, teams, users
from app.core.config import get_settings
from app.core.errors import DomainError, ProblemDetails
from app.db.client import mongo_manager
from app.db.indexes import ensure_indexes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("opsboard")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup and shutdown hooks."""
    cfg = get_settings()
    logger.info("Initializing MongoDB connection pool to %s...", cfg.MONGODB_URI)
    try:
        await mongo_manager.connect()
        db = mongo_manager.get_database()
        logger.info("Ensuring database indexes...")
        await ensure_indexes(db)
        logger.info("Opsboard backend ready.")
    except Exception as e:
        logger.warning("MongoDB initialization notice: %s. Continuing startup...", e)
    yield
    logger.info("Shutting down MongoDB connection pool...")
    await mongo_manager.close()


app = FastAPI(
    title="Opsboard API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/api/v1/openapi.json",
    lifespan=lifespan,
)

# CORS
cfg = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[cfg.APP_ORIGIN, "http://localhost:3000", "http://localhost:8080", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["ETag", "Location", "Idempotent-Replay", "X-Request-ID"],
)


@app.middleware("http")
async def request_id_and_logging_middleware(request: Request, call_next):
    """Assign X-Request-ID and attach to response."""
    req_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    request.state.request_id = req_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = req_id
    return response


# RFC 7807 Problem Details Error Handlers
@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    req_id = getattr(request.state, "request_id", None)
    problem = exc.to_problem_details(request_id=req_id)
    return JSONResponse(
        status_code=exc.status_code,
        content=problem.model_dump(),
        media_type="application/problem+json",
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    req_id = getattr(request.state, "request_id", None)
    errors = [{"loc": list(err["loc"]), "msg": err["msg"], "type": err["type"]} for err in exc.errors()]
    problem = ProblemDetails(
        type="https://opsboard.dev/errors/validation-failed",
        title="Validation Failed",
        status=422,
        code="VALIDATION_FAILED",
        detail="The request body or query parameters failed schema validation.",
        request_id=req_id,
        errors=errors,
    )
    return JSONResponse(
        status_code=422,
        content=problem.model_dump(),
        media_type="application/problem+json",
    )


@app.exception_handler(DuplicateKeyError)
async def duplicate_key_handler(request: Request, exc: DuplicateKeyError) -> JSONResponse:
    """Handle MongoDB duplicate key errors as 409 Conflict."""
    req_id = getattr(request.state, "request_id", None)
    logger.warning("Duplicate key error [req_id=%s]: %s", req_id, exc)
    problem = ProblemDetails(
        type="https://opsboard.dev/errors/conflict",
        title="Conflict",
        status=409,
        code="DUPLICATE_KEY",
        detail="A record with the same unique key already exists.",
        request_id=req_id,
    )
    return JSONResponse(
        status_code=409,
        content=problem.model_dump(),
        media_type="application/problem+json",
    )


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    req_id = getattr(request.state, "request_id", None)
    logger.exception("Unhandled server exception [req_id=%s]: %s", req_id, exc)
    problem = ProblemDetails(
        type="https://opsboard.dev/errors/internal-error",
        title="Internal Server Error",
        status=500,
        code="INTERNAL_ERROR",
        detail="An internal error occurred. Please reference the request_id with engineering.",
        request_id=req_id,
    )
    return JSONResponse(
        status_code=500,
        content=problem.model_dump(),
        media_type="application/problem+json",
    )


# Health check
@app.get("/healthz", tags=["health"])
async def healthz():
    return {"status": "ok"}


# Register V1 Routers
api_v1_prefix = "/api/v1"
app.include_router(auth.router, prefix=api_v1_prefix)
app.include_router(teams.router, prefix=api_v1_prefix)
app.include_router(items.router, prefix=api_v1_prefix)
app.include_router(approvals.router, prefix=api_v1_prefix)
app.include_router(overview.router, prefix=api_v1_prefix)
app.include_router(notifications.router, prefix=api_v1_prefix)
app.include_router(ai.router, prefix=api_v1_prefix)
app.include_router(search.router, prefix=api_v1_prefix)
app.include_router(features.router, prefix=api_v1_prefix)
app.include_router(stream.router, prefix=api_v1_prefix)
app.include_router(users.router, prefix=api_v1_prefix)
