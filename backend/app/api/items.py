"""
Work items API endpoints.
Implements CAS claims, optimistic ETag / If-Match locking, transactional idempotency,
and keyset pagination. Matches docs/API_SPEC.md §3.3.
"""

from datetime import datetime
import json
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import BaseModel, Field, model_validator
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import (
    get_current_user_and_memberships,
    get_optional_if_match,
    get_required_idempotency_key,
    get_required_if_match,
)
from app.core.errors import DomainError
from app.db.client import get_database
from app.db.uow import UnitOfWork, get_uow
from app.domain.enums import ItemPriority, ItemResolution, ItemStatus, ItemType
from app.infra.idempotency import IdempotencyService, compute_request_hash
from app.services.item_service import ItemService

router = APIRouter(prefix="/items", tags=["items"])


# Request / Response Schemas
class CreateItemRequest(BaseModel):
    team_id: str
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=20000)
    type: ItemType = ItemType.CUSTOMER_ISSUE
    priority: ItemPriority = ItemPriority.P2
    due_at: Optional[datetime] = None
    tags: List[str] = Field(default_factory=list, max_length=10)


class UpdateItemRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)
    description: Optional[str] = Field(default=None, max_length=20000)
    priority: Optional[ItemPriority] = None
    due_at: Optional[datetime] = None
    tags: Optional[List[str]] = None


class TransitionRequest(BaseModel):
    to_status: Optional[ItemStatus] = None
    to: Optional[ItemStatus] = None
    reason: Optional[str] = Field(default=None, max_length=1000)
    resolution: Optional[ItemResolution] = None
    duplicate_of: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def populate_to(cls, data: Any) -> Any:
        if isinstance(data, dict):
            target = data.get("to") or data.get("to_status")
            if target:
                data["to_status"] = target
                data["to"] = target
        return data


class CommentRequest(BaseModel):
    body: str = Field(min_length=1, max_length=10000)


@router.post("", status_code=201)
async def create_item(
    payload: CreateItemRequest,
    request: Request,
    response: Response,
    idempotency_key: str = Depends(get_required_idempotency_key),
    auth_data: tuple = Depends(get_current_user_and_memberships),
    db: AsyncDatabase = Depends(get_database),
    uow: UnitOfWork = Depends(get_uow),
):
    """
    Create a new operational work item.
    Requires `Idempotency-Key` header. Returns 201 with Location and ETag.
    """
    user, memberships = auth_data
    body_bytes = await request.body()
    req_hash = compute_request_hash("POST", "/api/v1/items", body_bytes)

    # 1. Check idempotency cache first
    cached = await IdempotencyService.get_stored_response(db, user["id"], idempotency_key, req_hash)
    if cached:
        status, body, headers = cached
        for k, v in headers.items():
            response.headers[k] = v
        response.status_code = status
        return body

    service = ItemService(db, uow)
    item = await service.create_item(
        actor_id=user["id"],
        actor_name=user["name"],
        is_org_admin=user.get("is_org_admin", False),
        memberships=memberships,
        team_id=payload.team_id,
        title=payload.title,
        description=payload.description,
        item_type=payload.type,
        priority=payload.priority,
        due_at=payload.due_at,
        tags=payload.tags,
        idempotency_key=idempotency_key,
        request_hash=req_hash,
    )

    response.headers["ETag"] = f'"{item["version"]}"'
    response.headers["Location"] = f"/api/v1/items/{item['_id']}"
    return item


@router.get("")
async def list_items(
    view: Optional[str] = Query(None),
    team_id: Optional[List[str]] = Query(None),
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    assignee_id: Optional[str] = Query(None),
    cursor: Optional[str] = Query(None),
    limit: int = Query(25, ge=1, le=100),
    auth_data: tuple = Depends(get_current_user_and_memberships),
    db: AsyncDatabase = Depends(get_database),
    uow: UnitOfWork = Depends(get_uow),
):
    """
    Keyset-paginated items list using compound index.
    Bounded reads only (max limit 100). No skip().
    """
    user, memberships = auth_data
    cursor_data = None
    if cursor:
        try:
            parts = cursor.split("|")
            if len(parts) == 3:
                c_prio = parts[0]
                c_updated = datetime.fromisoformat(parts[1])
                c_id = parts[2]
                cursor_data = (c_prio, c_updated, c_id)
            else:
                raise DomainError(detail="Invalid pagination cursor format.", code="BAD_CURSOR", status_code=400)
        except DomainError:
            raise
        except Exception:
            raise DomainError(detail="Invalid pagination cursor.", code="BAD_CURSOR", status_code=400)

    service = ItemService(db, uow)
    items, has_more = await service.list_items(
        actor_id=user["id"],
        is_org_admin=user.get("is_org_admin", False),
        memberships=memberships,
        team_ids=team_id,
        view=view,
        status=status,
        priority=priority,
        assignee_id=assignee_id,
        cursor_data=cursor_data,
        limit=limit,
    )

    for itm in items:
        if "_id" in itm and "id" not in itm:
            itm["id"] = itm["_id"]

    next_cursor = None
    if has_more and items:
        last = items[-1]
        next_cursor = f"{last['priority']}|{last['updated_at'].isoformat()}|{last['_id']}"

    return {
        "items": items,
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


@router.get("/{identifier}")
async def get_item(
    identifier: str,
    response: Response,
    auth_data: tuple = Depends(get_current_user_and_memberships),
    db: AsyncDatabase = Depends(get_database),
    uow: UnitOfWork = Depends(get_uow),
):
    """Retrieve item detail by ObjectId or key. Returns ETag header with version."""
    user, memberships = auth_data
    service = ItemService(db, uow)
    item = await service.get_item(
        identifier=identifier,
        actor_id=user["id"],
        is_org_admin=user.get("is_org_admin", False),
        memberships=memberships,
    )
    response.headers["ETag"] = f'"{item["version"]}"'
    return item


@router.patch("/{identifier}")
async def patch_item(
    identifier: str,
    payload: UpdateItemRequest,
    response: Response,
    expected_version: int = Depends(get_required_if_match),
    auth_data: tuple = Depends(get_current_user_and_memberships),
    db: AsyncDatabase = Depends(get_database),
    uow: UnitOfWork = Depends(get_uow),
):
    """
    Optimistic locking field edit.
    Requires `If-Match: "<version>"`. Stale writes receive 412 VERSION_CONFLICT.
    """
    user, memberships = auth_data
    service = ItemService(db, uow)
    updated = await service.update_item_fields(
        actor_id=user["id"],
        actor_name=user["name"],
        is_org_admin=user.get("is_org_admin", False),
        memberships=memberships,
        item_id=identifier,
        expected_version=expected_version,
        title=payload.title,
        description=payload.description,
        priority=payload.priority,
        due_at=payload.due_at,
        tags=payload.tags,
    )
    response.headers["ETag"] = f'"{updated["version"]}"'
    return updated


@router.post("/{identifier}/claim")
async def claim_item(
    identifier: str,
    request: Request,
    response: Response,
    idempotency_key: str = Depends(get_required_idempotency_key),
    auth_data: tuple = Depends(get_current_user_and_memberships),
    db: AsyncDatabase = Depends(get_database),
    uow: UnitOfWork = Depends(get_uow),
):
    """
    Atomic compare-and-set claim. Exactly one winner claims;
    loser receives 409 ALREADY_CLAIMED naming winner.
    """
    user, memberships = auth_data
    body_bytes = await request.body()
    req_hash = compute_request_hash("POST", f"/api/v1/items/{identifier}/claim", body_bytes)

    cached = await IdempotencyService.get_stored_response(db, user["id"], idempotency_key, req_hash)
    if cached:
        status, body, headers = cached
        for k, v in headers.items():
            response.headers[k] = v
        response.status_code = status
        return body

    service = ItemService(db, uow)
    updated = await service.claim_item(
        actor_id=user["id"],
        actor_name=user["name"],
        is_org_admin=user.get("is_org_admin", False),
        memberships=memberships,
        item_id=identifier,
        idempotency_key=idempotency_key,
        request_hash=req_hash,
    )
    response.headers["ETag"] = f'"{updated["version"]}"'
    return updated


@router.post("/{identifier}/release")
async def release_item(
    identifier: str,
    request: Request,
    response: Response,
    idempotency_key: str = Depends(get_required_idempotency_key),
    auth_data: tuple = Depends(get_current_user_and_memberships),
    db: AsyncDatabase = Depends(get_database),
    uow: UnitOfWork = Depends(get_uow),
):
    """Atomic release of an item assigned to caller."""
    user, memberships = auth_data
    body_bytes = await request.body()
    req_hash = compute_request_hash("POST", f"/api/v1/items/{identifier}/release", body_bytes)

    cached = await IdempotencyService.get_stored_response(db, user["id"], idempotency_key, req_hash)
    if cached:
        status, body, headers = cached
        for k, v in headers.items():
            response.headers[k] = v
        response.status_code = status
        return body

    service = ItemService(db, uow)
    updated = await service.release_item(
        actor_id=user["id"],
        actor_name=user["name"],
        is_org_admin=user.get("is_org_admin", False),
        memberships=memberships,
        item_id=identifier,
        idempotency_key=idempotency_key,
        request_hash=req_hash,
    )
    response.headers["ETag"] = f'"{updated["version"]}"'
    return updated


@router.post("/{identifier}/transitions")
async def transition_item(
    identifier: str,
    payload: TransitionRequest,
    request: Request,
    response: Response,
    expected_version: int = Depends(get_required_if_match),
    idempotency_key: str = Depends(get_required_idempotency_key),
    auth_data: tuple = Depends(get_current_user_and_memberships),
    db: AsyncDatabase = Depends(get_database),
    uow: UnitOfWork = Depends(get_uow),
):
    """
    Execute workflow state machine transition with role and reason checks.
    Requires `If-Match` and `Idempotency-Key`.
    """
    user, memberships = auth_data
    body_bytes = await request.body()
    req_hash = compute_request_hash("POST", f"/api/v1/items/{identifier}/transitions", body_bytes)

    cached = await IdempotencyService.get_stored_response(db, user["id"], idempotency_key, req_hash)
    if cached:
        status, body, headers = cached
        for k, v in headers.items():
            response.headers[k] = v
        response.status_code = status
        return body

    service = ItemService(db, uow)
    updated = await service.transition_item(
        actor_id=user["id"],
        actor_name=user["name"],
        is_org_admin=user.get("is_org_admin", False),
        memberships=memberships,
        item_id=identifier,
        to_status=payload.to_status,
        expected_version=expected_version,
        reason=payload.reason,
        resolution=payload.resolution,
        duplicate_of=payload.duplicate_of,
        idempotency_key=idempotency_key,
        request_hash=req_hash,
    )
    response.headers["ETag"] = f'"{updated["version"]}"'
    return updated


@router.post("/{identifier}/comments", status_code=201)
async def add_comment(
    identifier: str,
    payload: CommentRequest,
    request: Request,
    response: Response,
    idempotency_key: str = Depends(get_required_idempotency_key),
    auth_data: tuple = Depends(get_current_user_and_memberships),
    db: AsyncDatabase = Depends(get_database),
    uow: UnitOfWork = Depends(get_uow),
):
    """
    Post an immutable timeline comment.
    Comments do NOT bump item version (chatting never invalidates concurrent edits).
    """
    user, memberships = auth_data
    body_bytes = await request.body()
    req_hash = compute_request_hash("POST", f"/api/v1/items/{identifier}/comments", body_bytes)

    cached = await IdempotencyService.get_stored_response(db, user["id"], idempotency_key, req_hash)
    if cached:
        status, body, headers = cached
        for k, v in headers.items():
            response.headers[k] = v
        response.status_code = status
        return body

    service = ItemService(db, uow)
    event_doc = await service.add_comment(
        actor_id=user["id"],
        actor_name=user["name"],
        is_org_admin=user.get("is_org_admin", False),
        memberships=memberships,
        item_id=identifier,
        body=payload.body,
        idempotency_key=idempotency_key,
        request_hash=req_hash,
    )
    return event_doc


@router.get("/{identifier}/timeline")
async def get_item_timeline(
    identifier: str,
    since_seq: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    auth_data: tuple = Depends(get_current_user_and_memberships),
    db: AsyncDatabase = Depends(get_database),
    uow: UnitOfWork = Depends(get_uow),
):
    """Retrieve ordered audit timeline events for an item."""
    user, memberships = auth_data
    service = ItemService(db, uow)
    events = await service.get_timeline(
        identifier=identifier,
        actor_id=user["id"],
        is_org_admin=user.get("is_org_admin", False),
        memberships=memberships,
        since_seq=since_seq,
        limit=limit,
    )
    return {"events": events}
