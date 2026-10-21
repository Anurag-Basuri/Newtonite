"""
Transactional Outbox domain models for reliable asynchronous side effects.
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import Field

from app.domain.enums import OutboxStatus, OutboxType
from app.domain.models.base import BaseSchema, MongoDocument, generate_id, utc_now


class OutboxMessage(MongoDocument):
    """
    Message stored in 'outbox' collection within the same transaction as state changes.
    Guarantees at-least-once delivery to async handlers (search/RAG indexing, notifications).
    """
    id: str = Field(default_factory=lambda: generate_id("out"), alias="_id")
    type: OutboxType
    payload: Dict[str, Any] = Field(default_factory=dict)
    status: OutboxStatus = OutboxStatus.PENDING

    attempts: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=6, ge=1)
    lease_until: Optional[datetime] = None
    last_error: Optional[str] = None
    next_attempt_at: datetime = Field(default_factory=utc_now)
    correlation_id: Optional[str] = None


class OutboxMessageResponse(BaseSchema):
    """Admin inspection view of outbox messages."""
    id: str
    type: OutboxType
    payload: Dict[str, Any]
    status: OutboxStatus
    attempts: int
    max_attempts: int
    lease_until: Optional[datetime] = None
    last_error: Optional[str] = None
    next_attempt_at: datetime
    correlation_id: Optional[str] = None
    created_at: datetime


class NotifyPayload(BaseSchema):
    """Payload stored in outbox for asynchronous notifications dispatch."""
    event_id: str
    item_id: str
    item_key: str
    team_id: str
    event_type: str
    actor_id: str
    title: str
    body: str
    recipient_user_ids: List[str]


class IndexItemPayload(BaseSchema):
    """Payload stored in outbox for asynchronous RAG/search chunk indexing."""
    item_id: str
    item_key: str
    team_id: str
    content_version: int
