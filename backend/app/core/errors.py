"""
Domain errors and RFC 7807 Problem Details representation.
Enforces catalogued error codes across all domain layers and routers.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ProblemDetails(BaseModel):
    """
    Standard RFC 7807 Problem Details response payload.
    Ensures safe, structured errors without leaking internals or stack traces.
    """
    type: str = "about:blank"
    title: str
    status: int
    code: str
    detail: str
    request_id: Optional[str] = None
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    meta: Dict[str, Any] = Field(default_factory=dict)


class DomainError(Exception):
    """Base class for all business and domain exceptions."""
    status_code: int = 500
    code: str = "INTERNAL_ERROR"
    title: str = "Internal Server Error"

    def __init__(
        self,
        detail: Optional[str] = None,
        *,
        code: Optional[str] = None,
        status_code: Optional[int] = None,
        message: Optional[str] = None,
        errors: Optional[List[Dict[str, Any]]] = None,
        meta: Optional[Dict[str, Any]] = None,
    ):
        text = detail or message or "An error occurred."
        super().__init__(text)
        self.detail = text
        if code:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        self.errors = errors or []
        self.meta = meta or {}

    def to_problem_details(self, request_id: Optional[str] = None) -> ProblemDetails:
        return ProblemDetails(
            type=f"https://opsboard.dev/errors/{self.code.lower().replace('_', '-')}",
            title=self.title,
            status=self.status_code,
            code=self.code,
            detail=self.detail,
            request_id=request_id,
            errors=self.errors,
            meta=self.meta,
        )


class UnauthenticatedError(DomainError):
    status_code = 401
    code = "UNAUTHENTICATED"
    title = "Authentication Required"


class ForbiddenError(DomainError):
    status_code = 403
    code = "FORBIDDEN"
    title = "Forbidden"


class NotFoundError(DomainError):
    status_code = 404
    code = "NOT_FOUND"
    title = "Not Found"


class ConflictError(DomainError):
    status_code = 409
    code = "CONFLICT"
    title = "Conflict"


class AlreadyClaimedError(ConflictError):
    code = "ALREADY_CLAIMED"
    title = "Item Already Claimed"

    def __init__(self, current_assignee_id: Optional[str] = None, detail: str = "This item has already been claimed by another user."):
        meta = {"winner_id": current_assignee_id} if current_assignee_id else {}
        super().__init__(detail=detail, code=self.code, meta=meta)


class PreconditionRequiredError(DomainError):
    status_code = 428
    code = "PRECONDITION_REQUIRED"
    title = "Precondition Required"


class PreconditionFailedError(DomainError):
    status_code = 412
    code = "VERSION_CONFLICT"
    title = "Version Conflict"


class IdempotencyConflictError(ConflictError):
    code = "IDEMPOTENCY_CONFLICT"
    title = "Idempotency Conflict"


class RateLimitExceededError(DomainError):
    status_code = 429
    code = "RATE_LIMITED"
    title = "Too Many Requests"


class ValidationError(DomainError):
    status_code = 422
    code = "VALIDATION_FAILED"
    title = "Validation Failed"
