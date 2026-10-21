"""
In-app notification domain models with deduplication keys.
"""

from datetime import datetime
from typing import Optional
from pydantic import Field

from app.domain.models.base import BaseSchema, MongoDocument, generate_id


class Notification(MongoDocument):
    """
    In-app user notification.
    Unique constraint on `dedupe_key` ensures worker retries do not spam users.
    """
    id: str = Field(default_factory=lambda: generate_id("notif"), alias="_id")
    user_id: str
    dedupe_key: str = Field(description="Unique idempotency key, e.g. evt_123:usr_456")
    item_id: str
    item_key: str
    title: str = Field(max_length=200)
    body: str = Field(max_length=1000)
    read: bool = False
    read_at: Optional[datetime] = None


class NotificationResponse(BaseSchema):
    """Notification response for UI notifications dropdown / feed."""
    id: str
    item_id: str
    item_key: str
    title: str
    body: str
    read: bool
    read_at: Optional[datetime] = None
    created_at: datetime
