"""
Domain models and schema definitions for Opsboard.
"""

from app.domain.models.base import (
    BaseSchema,
    MongoDocument,
    generate_id,
    utc_now,
)
from app.domain.models.user import (
    User,
    UserCreate,
    UserResponse,
    LoginRequest,
    Membership,
    MembershipCreate,
    MembershipResponse,
    Session,
    UserContext,
)
from app.domain.models.team import (
    Team,
    TeamCreate,
    TeamResponse,
    TeamWithMemberships,
)
from app.domain.models.work_item import (
    SLA_WINDOWS,
    calculate_attention_due_at,
    WorkItem,
    WorkItemCreate,
    WorkItemUpdate,
    WorkItemSummary,
    WorkItemResponse,
    WorkItemTransitionRequest,
    WorkItemAssignRequest,
)
from app.domain.models.event import (
    ItemEvent,
    ItemEventResponse,
    CreateCommentRequest,
    CommentData,
    TransitionData,
    AssignmentData,
    UpdateData,
)
from app.domain.models.approval import (
    Approval,
    ApprovalRequestCreate,
    ApprovalDecisionRequest,
    ApprovalResponse,
)
from app.domain.models.outbox import (
    OutboxMessage,
    OutboxMessageResponse,
    NotifyPayload,
    IndexItemPayload,
)
from app.domain.models.notification import (
    Notification,
    NotificationResponse,
)
from app.domain.models.idempotency import (
    IdempotencyRecord,
)
from app.domain.models.ai import (
    ItemChunk,
    SimilarItemMatch,
    SimilarItemsResponse,
    AskQuestionRequest,
    Citation,
    AskQuestionResponse,
)
from app.domain.models.overview import (
    AttentionBucketSummary,
    OverviewResponse,
)

__all__ = [
    "BaseSchema",
    "MongoDocument",
    "generate_id",
    "utc_now",
    "User",
    "UserCreate",
    "UserResponse",
    "LoginRequest",
    "Membership",
    "MembershipCreate",
    "MembershipResponse",
    "Session",
    "UserContext",
    "Team",
    "TeamCreate",
    "TeamResponse",
    "TeamWithMemberships",
    "SLA_WINDOWS",
    "calculate_attention_due_at",
    "WorkItem",
    "WorkItemCreate",
    "WorkItemUpdate",
    "WorkItemSummary",
    "WorkItemResponse",
    "WorkItemTransitionRequest",
    "WorkItemAssignRequest",
    "ItemEvent",
    "ItemEventResponse",
    "CreateCommentRequest",
    "CommentData",
    "TransitionData",
    "AssignmentData",
    "UpdateData",
    "Approval",
    "ApprovalRequestCreate",
    "ApprovalDecisionRequest",
    "ApprovalResponse",
    "OutboxMessage",
    "OutboxMessageResponse",
    "NotifyPayload",
    "IndexItemPayload",
    "Notification",
    "NotificationResponse",
    "IdempotencyRecord",
    "ItemChunk",
    "SimilarItemMatch",
    "SimilarItemsResponse",
    "AskQuestionRequest",
    "Citation",
    "AskQuestionResponse",
    "AttentionBucketSummary",
    "OverviewResponse",
]
