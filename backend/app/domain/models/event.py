"""
Timeline and append-only audit event domain models.
"""

from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import Field

from app.domain.enums import EventType, ItemStatus, ItemResolution
from app.domain.models.base import BaseSchema, MongoDocument, generate_id, utc_now


class ItemEvent(MongoDocument):
    """
    Append-only audit event stored in 'item_events' collection.
    Guarantees full provenance: who did what, when, and why.
    """
    id: str = Field(default_factory=lambda: generate_id("evt"), alias="_id")
    item_id: str
    team_id: str
    seq: int = Field(ge=1, description="Item-scoped monotonic sequence number")
    type: EventType
    actor_id: str
    actor_name: str
    data: Dict[str, Any] = Field(default_factory=dict)
    correlation_id: Optional[str] = None


class ItemEventResponse(BaseSchema):
    """Event representation for timeline UI rendering."""
    id: str
    item_id: str
    team_id: str
    seq: int
    type: EventType
    actor_id: str
    actor_name: str
    data: Dict[str, Any]
    created_at: datetime


class CreateCommentRequest(BaseSchema):
    """Payload to post a comment on an item."""
    body: str = Field(min_length=1, max_length=10000)


class CommentData(BaseSchema):
    """Typed data payload for ITEM_COMMENTED events."""
    body: str


class TransitionData(BaseSchema):
    """Typed data payload for ITEM_TRANSITIONED events."""
    from_status: ItemStatus
    to_status: ItemStatus
    reason: Optional[str] = None
    resolution: Optional[ItemResolution] = None
    duplicate_of: Optional[str] = None


class AssignmentData(BaseSchema):
    """Typed data payload for ITEM_ASSIGNED / CLAIMED / RELEASED events."""
    previous_assignee_id: Optional[str] = None
    new_assignee_id: Optional[str] = None
    action: str  # "claimed", "released", "assigned"


class UpdateData(BaseSchema):
    """Typed data payload for ITEM_UPDATED field diffs."""
    changes: Dict[str, Dict[str, Any]]  # field_name -> {"old": ..., "new": ...}
