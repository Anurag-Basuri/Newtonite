"""
FastAPI route dependencies for authentication, headers, and service injection.
"""

import hashlib
import json
from typing import Any, Dict, List, Optional, Tuple
from fastapi import Cookie, Depends, Header, Request
from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import get_settings
from app.core.errors import (
    DomainError,
    PreconditionRequiredError,
    UnauthenticatedError,
    ValidationError,
)
from app.db.client import get_database, get_mongo_client
from app.db.uow import UnitOfWork, get_uow
from app.infra.idempotency import IdempotencyService, compute_request_hash
from app.services.auth_service import AuthService
from app.services.item_service import ItemService
from app.services.approval_service import ApprovalService
from app.services.overview_service import OverviewService
from app.repositories.notifications import NotificationRepository
from app.repositories.teams import TeamRepository


async def get_current_user_and_memberships(
    request: Request,
    db: AsyncDatabase = Depends(get_database),
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Extract session cookie and return authenticated (user, memberships).
    """
    cfg = get_settings()
    token = request.cookies.get(cfg.COOKIE_NAME)
    auth_service = AuthService(db)
    return await auth_service.get_current_user_and_memberships(token)


async def get_required_if_match(
    if_match: Optional[str] = Header(None, alias="If-Match"),
) -> int:
    """
    Ensure `If-Match: "<version>"` header is present for optimistic locking.
    Raises 428 PRECONDITION_REQUIRED if absent.
    """
    if not if_match:
        raise PreconditionRequiredError(
            detail="If-Match header with current version is required for this operation."
        )
    clean_val = if_match.strip().strip('"')
    try:
        return int(clean_val)
    except ValueError:
        raise ValidationError(detail="If-Match must contain an integer version.")


async def get_optional_if_match(
    if_match: Optional[str] = Header(None, alias="If-Match"),
) -> Optional[int]:
    if not if_match:
        return None
    clean_val = if_match.strip().strip('"')
    try:
        return int(clean_val)
    except ValueError:
        return None


async def get_required_idempotency_key(
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> str:
    """
    Ensure `Idempotency-Key` header is present on mutating POST operations.
    """
    if not idempotency_key or not idempotency_key.strip():
        raise ValidationError(
            detail="Idempotency-Key header is required on mutating POST operations."
        )
    return idempotency_key.strip()
