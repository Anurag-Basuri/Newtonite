"""
Domain enumerations for Opsboard (Operations Under Pressure).
Defines all domain statuses, roles, types, priorities, and event classifications.
"""

from enum import Enum


class StrEnum(str, Enum):
    """String enum for seamless Pydantic and JSON serialization."""
    def __str__(self) -> str:
        return str(self.value)


class ItemStatus(StrEnum):
    """Workflow states for work items."""
    OPEN = "open"
    TRIAGED = "triaged"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    PENDING_APPROVAL = "pending_approval"
    RESOLVED = "resolved"
    CLOSED = "closed"

    @classmethod
    def terminal_states(cls) -> set["ItemStatus"]:
        return {cls.CLOSED}

    @classmethod
    def active_states(cls) -> set["ItemStatus"]:
        return {cls.OPEN, cls.TRIAGED, cls.IN_PROGRESS, cls.BLOCKED, cls.PENDING_APPROVAL, cls.RESOLVED}


class ItemPriority(StrEnum):
    """Urgency / business priority levels."""
    P0 = "P0"  # Critical / Outage / Immediate SLA (1 hour)
    P1 = "P1"  # High / Escalation (4 hours)
    P2 = "P2"  # Medium / Normal operational work (24 hours)
    P3 = "P3"  # Low / Minor backlog (72 hours)


class ItemType(StrEnum):
    """Operational work item categories matching the challenge brief and domain model."""
    CUSTOMER_ISSUE = "customer_issue"
    ENGINEERING = "engineering"
    PAYMENT = "payment"
    INCIDENT = "incident"
    COMPLIANCE = "compliance"
    TASK = "task"

    # Aliases for flexibility and backwards compatibility
    ISSUE = "customer_issue"
    INVESTIGATION = "payment"
    APPROVAL_REQUEST = "compliance"
    OPERATIONAL_TASK = "task"


class ItemResolution(StrEnum):
    """Reason for closing an item."""
    COMPLETED = "completed"
    WONT_DO = "wont_do"
    DUPLICATE = "duplicate"
    CANCELLED = "cancelled"


class TeamRole(StrEnum):
    """Hierarchical team permissions (viewer < member < lead)."""
    VIEWER = "viewer"
    MEMBER = "member"
    LEAD = "lead"

    def __ge__(self, other: "TeamRole") -> bool:
        hierarchy = {TeamRole.VIEWER: 1, TeamRole.MEMBER: 2, TeamRole.LEAD: 3}
        if isinstance(other, TeamRole):
            return hierarchy[self] >= hierarchy[other]
        return NotImplemented

    def __gt__(self, other: "TeamRole") -> bool:
        hierarchy = {TeamRole.VIEWER: 1, TeamRole.MEMBER: 2, TeamRole.LEAD: 3}
        if isinstance(other, TeamRole):
            return hierarchy[self] > hierarchy[other]
        return NotImplemented


class EventType(StrEnum):
    """Audit events recorded in the append-only item_events timeline."""
    ITEM_CREATED = "item.created"
    ITEM_UPDATED = "item.updated"
    ITEM_CLAIMED = "item.claimed"
    ITEM_RELEASED = "item.released"
    ITEM_ASSIGNED = "item.assigned"
    ITEM_TRANSITIONED = "item.transitioned"
    ITEM_COMMENTED = "item.commented"
    APPROVAL_REQUESTED = "item.approval_requested"
    APPROVAL_DECIDED = "item.approval_decided"
    ITEM_REOPENED = "item.reopened"
    ITEM_CLOSED = "item.closed"


class ApprovalStatus(StrEnum):
    """Lifecycle status of a sensitive item approval."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class OutboxStatus(StrEnum):
    """Status of an asynchronous message in the transactional outbox."""
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    COMPLETED = "done"
    DEAD = "dead"


class OutboxType(StrEnum):
    """Async task classifications."""
    NOTIFY = "notify"
    INDEX_ITEM = "index_item"
    EMAIL_STUB = "email_stub"


class ChunkKind(StrEnum):
    """Kind of operational knowledge embedded in vector storage."""
    ITEM = "item"
    COMMENT = "comment"
    DECISION = "decision"


class AttentionReason(StrEnum):
    """Reason an operational work item requires immediate focus."""
    AWAITING_MY_APPROVAL = "awaiting_my_approval"
    OVERDUE_MINE = "overdue_mine"
    UNOWNED_URGENT = "unowned_urgent"
    STALE = "stale"
    BLOCKED_MINE = "blocked_mine"
    MINE = "mine"
    CREATED_BY_ME = "created_by_me"
