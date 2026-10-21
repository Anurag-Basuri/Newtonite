"""
Approvals API endpoints.
Enforces four-eyes rule and atomic approval decisions.
Matches docs/API_SPEC.md §3.4.
"""

from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field, model_validator
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import (
    get_current_user_and_memberships,
    get_required_idempotency_key,
    get_required_if_match,
)
from app.db.client import get_database
from app.db.uow import UnitOfWork, get_uow
from app.infra.idempotency import IdempotencyService, compute_request_hash
from app.services.approval_service import ApprovalService

router = APIRouter(tags=["approvals"])


class RequestApprovalBody(BaseModel):
    request_note: str = Field(min_length=1, max_length=1000)


class DecideApprovalBody(BaseModel):
    approved: Optional[bool] = None
    decision: Optional[str] = None
    decision_reason: Optional[str] = Field(default=None, max_length=1000)
    reason: Optional[str] = Field(default=None, max_length=1000)

    @model_validator(mode="before")
    @classmethod
    def populate_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "decision" in data and "approved" not in data:
                data["approved"] = str(data["decision"]).strip().lower() == "approve"
            elif "approved" in data and "decision" not in data:
                data["decision"] = "approve" if data["approved"] else "reject"
            if "reason" in data and "decision_reason" not in data:
                data["decision_reason"] = data["reason"]
            elif "decision_reason" in data and "reason" not in data:
                data["reason"] = data["decision_reason"]
            if not data.get("decision_reason"):
                data["decision_reason"] = "Approved by lead" if data.get("approved") else "Rejected by lead"
        return data


@router.post("/items/{identifier}/approval")
async def request_approval(
    identifier: str,
    payload: RequestApprovalBody,
    request: Request,
    response: Response,
    expected_version: int = Depends(get_required_if_match),
    idempotency_key: str = Depends(get_required_idempotency_key),
    auth_data: tuple = Depends(get_current_user_and_memberships),
    db: AsyncDatabase = Depends(get_database),
    uow: UnitOfWork = Depends(get_uow),
):
    """
    Request approval for a work item.
    Transitions item to PENDING_APPROVAL and creates approval record.
    """
    user, memberships = auth_data
    body_bytes = await request.body()
    req_hash = compute_request_hash("POST", f"/api/v1/items/{identifier}/approval", body_bytes)

    cached = await IdempotencyService.get_stored_response(db, user["id"], idempotency_key, req_hash)
    if cached:
        status, body, headers = cached
        for k, v in headers.items():
            response.headers[k] = v
        response.status_code = status
        return body

    service = ApprovalService(db, uow)
    approval_doc = await service.request_approval(
        actor_id=user["id"],
        actor_name=user["name"],
        is_org_admin=user.get("is_org_admin", False),
        memberships=memberships,
        item_id=identifier,
        request_note=payload.request_note,
        expected_version=expected_version,
        idempotency_key=idempotency_key,
        request_hash=req_hash,
    )
    return approval_doc


@router.post("/approvals/{approval_id}/decision")
async def decide_approval(
    approval_id: str,
    payload: DecideApprovalBody,
    request: Request,
    response: Response,
    idempotency_key: str = Depends(get_required_idempotency_key),
    auth_data: tuple = Depends(get_current_user_and_memberships),
    db: AsyncDatabase = Depends(get_database),
    uow: UnitOfWork = Depends(get_uow),
):
    """
    Decide an approval request (approve or reject).
    ENFORCES FOUR-EYES RULE: the decider CANNOT be the requester.
    """
    user, memberships = auth_data
    body_bytes = await request.body()
    req_hash = compute_request_hash("POST", f"/api/v1/approvals/{approval_id}/decision", body_bytes)

    cached = await IdempotencyService.get_stored_response(db, user["id"], idempotency_key, req_hash)
    if cached:
        status, body, headers = cached
        for k, v in headers.items():
            response.headers[k] = v
        response.status_code = status
        return body

    service = ApprovalService(db, uow)
    result = await service.decide_approval(
        actor_id=user["id"],
        actor_name=user["name"],
        is_org_admin=user.get("is_org_admin", False),
        memberships=memberships,
        approval_id=approval_id,
        approved=payload.approved,
        decision_reason=payload.decision_reason,
        idempotency_key=idempotency_key,
        request_hash=req_hash,
    )
    return result
