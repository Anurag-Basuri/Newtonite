"""
Approvals domain models and four-eyes rule enforcement structures.
"""

from datetime import datetime
from typing import Optional
from pydantic import Field

from app.domain.enums import ApprovalStatus
from app.domain.models.base import BaseSchema, MongoDocument, generate_id, utc_now


class Approval(MongoDocument):
    """
    Approval entity stored in 'approvals' collection.
    Sensitive operational actions require formal sign-off.
    """
    id: str = Field(default_factory=lambda: generate_id("appr"), alias="_id")
    item_id: str
    team_id: str
    requested_by: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    reason: str = Field(min_length=1, max_length=1000)

    decided_by: Optional[str] = None
    decision_reason: Optional[str] = Field(default=None, max_length=1000)
    requested_at: datetime = Field(default_factory=utc_now)
    decided_at: Optional[datetime] = None


class ApprovalRequestCreate(BaseSchema):
    """Payload to initiate an approval request."""
    reason: str = Field(min_length=1, max_length=1000)


class ApprovalDecisionRequest(BaseSchema):
    """Payload for lead to approve or reject."""
    decision: ApprovalStatus = Field(description="Must be approved or rejected")
    reason: Optional[str] = Field(default=None, max_length=1000)


class ApprovalResponse(BaseSchema):
    """Public approval record view."""
    id: str
    item_id: str
    team_id: str
    requested_by: str
    status: ApprovalStatus
    reason: str
    decided_by: Optional[str] = None
    decision_reason: Optional[str] = None
    requested_at: datetime
    decided_at: Optional[datetime] = None
