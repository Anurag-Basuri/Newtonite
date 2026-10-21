"""
Work Item domain models, validation, and DTOs.
"""

from datetime import datetime, timedelta
from typing import Optional, List
from pydantic import Field, field_validator

from app.domain.enums import ItemStatus, ItemPriority, ItemType, ItemResolution
from app.domain.models.base import BaseSchema, MongoDocument, generate_id, utc_now


SLA_WINDOWS: dict[ItemPriority, timedelta] = {
    ItemPriority.P0: timedelta(hours=1),
    ItemPriority.P1: timedelta(hours=4),
    ItemPriority.P2: timedelta(hours=24),
    ItemPriority.P3: timedelta(hours=72),
}


def calculate_attention_due_at(
    priority: ItemPriority,
    status: ItemStatus,
    base_time: Optional[datetime] = None,
) -> datetime:
    """
    Calculate the timestamp when this item becomes 'stale' or requires urgent attention.
    Blocked items have an attention window capped at 24 hours.
    """
    base = base_time or utc_now()
    window = SLA_WINDOWS.get(priority, timedelta(hours=24))
    if status == ItemStatus.BLOCKED:
        window = min(window, timedelta(hours=24))
    return base + window


class WorkItem(MongoDocument):
    """
    Core operational work item document stored in 'work_items' collection.
    Supports optimistic concurrency control via 'version'.
    """
    id: str = Field(default_factory=lambda: generate_id("itm"), alias="_id")
    team_id: str
    key: str = Field(description="Human readable key e.g. OPS-142", pattern=r"^[A-Z0-9]+-\d+$")
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=20000)
    type: ItemType = ItemType.ISSUE
    status: ItemStatus = ItemStatus.OPEN
    priority: ItemPriority = ItemPriority.P2

    reporter_id: str
    assignee_id: Optional[str] = None
    assigned_at: Optional[datetime] = None

    last_activity_at: datetime = Field(default_factory=utc_now)
    attention_due_at: datetime = Field(default_factory=lambda: calculate_attention_due_at(ItemPriority.P2, ItemStatus.OPEN))
    due_at: Optional[datetime] = None

    tags: List[str] = Field(default_factory=list, max_length=10)
    
    # Optimistic concurrency and timeline ordering
    version: int = Field(default=1, ge=1, description="Incremented on updates for optimistic locking")
    event_seq: int = Field(default=0, ge=0, description="Monotonically increasing sequence of events for this item")

    # Workflow metadata
    blocked_reason: Optional[str] = Field(default=None, max_length=1000)
    resolution: Optional[ItemResolution] = None
    duplicate_of: Optional[str] = Field(default=None, max_length=100)
    pending_approval_id: Optional[str] = None

    @field_validator("tags")
    @classmethod
    def sanitize_tags(cls, tags: List[str]) -> List[str]:
        cleaned = []
        for t in tags:
            tag_clean = t.strip().lower()
            if tag_clean and len(tag_clean) <= 30 and tag_clean not in cleaned:
                cleaned.append(tag_clean)
        return cleaned[:10]


class WorkItemCreate(BaseSchema):
    """Payload to create a new work item."""
    team_id: str
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=20000)
    type: ItemType = ItemType.ISSUE
    priority: ItemPriority = ItemPriority.P2
    due_at: Optional[datetime] = None
    tags: List[str] = Field(default_factory=list, max_length=10)
    assignee_id: Optional[str] = None


class WorkItemUpdate(BaseSchema):
    """
    Fields that can be patched with stale-write protection (requires If-Match).
    """
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=20000)
    priority: Optional[ItemPriority] = None
    due_at: Optional[datetime] = None
    tags: Optional[List[str]] = None


class WorkItemSummary(BaseSchema):
    """
    Lightweight projection for list views and search results.
    Avoids loading full 20KB description bodies into memory.
    """
    id: str
    team_id: str
    key: str
    title: str
    type: ItemType
    status: ItemStatus
    priority: ItemPriority
    assignee_id: Optional[str] = None
    reporter_id: str
    last_activity_at: datetime
    attention_due_at: datetime
    due_at: Optional[datetime] = None
    tags: List[str] = Field(default_factory=list)
    version: int


class WorkItemResponse(BaseSchema):
    """Full work item view including description and workflow flags."""
    id: str
    team_id: str
    key: str
    title: str
    description: str
    type: ItemType
    status: ItemStatus
    priority: ItemPriority
    reporter_id: str
    assignee_id: Optional[str] = None
    assigned_at: Optional[datetime] = None
    last_activity_at: datetime
    attention_due_at: datetime
    due_at: Optional[datetime] = None
    tags: List[str] = Field(default_factory=list)
    version: int
    event_seq: int
    blocked_reason: Optional[str] = None
    resolution: Optional[ItemResolution] = None
    duplicate_of: Optional[str] = None
    pending_approval_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class WorkItemTransitionRequest(BaseSchema):
    """Payload to advance item state."""
    to_status: ItemStatus
    reason: Optional[str] = Field(default=None, max_length=1000)
    resolution: Optional[ItemResolution] = None
    duplicate_of: Optional[str] = Field(default=None, max_length=100)


class WorkItemAssignRequest(BaseSchema):
    """Assign or reassign an item to another team member."""
    assignee_id: Optional[str] = None
