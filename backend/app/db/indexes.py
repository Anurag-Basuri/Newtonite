"""
Index definitions and setup for Opsboard.
Guarantees database-enforced correctness constraints, unique invariants,
partial unique constraints, TTLs, and compound keyset pagination indexes.
Matches docs/DATA_MODEL.md §3.
"""

from pymongo import IndexModel, ASCENDING, DESCENDING
from pymongo.asynchronous.database import AsyncDatabase


async def ensure_indexes(db: AsyncDatabase) -> None:
    """
    Ensure all application indexes exist with correct options.
    Idempotent: safe to run on startup or via `make indexes`.
    """
    # 1. users
    await db.users.create_indexes([
        IndexModel([("email", ASCENDING)], unique=True, name="uq_user_email"),
    ])

    # 2. teams
    await db.teams.create_indexes([
        IndexModel([("slug", ASCENDING)], unique=True, name="uq_team_slug"),
        IndexModel([("key_prefix", ASCENDING)], unique=True, name="uq_team_key_prefix"),
    ])

    # 3. memberships
    await db.memberships.create_indexes([
        IndexModel([("team_id", ASCENDING), ("user_id", ASCENDING)], unique=True, name="uq_membership_team_user"),
        IndexModel([("user_id", ASCENDING)], name="idx_membership_user"),
    ])

    # 4. sessions
    await db.sessions.create_indexes([
        IndexModel([("expires_at", ASCENDING)], expireAfterSeconds=0, name="ttl_session_expiry"),
        IndexModel([("user_id", ASCENDING)], name="idx_session_user"),
    ])

    # 5. work_items
    await db.work_items.create_indexes([
        IndexModel([("team_id", ASCENDING), ("key", ASCENDING)], unique=True, name="uq_item_team_key"),
        # Compound keyset pagination index: (team_id, priority, updated_at DESC, _id ASC)
        IndexModel(
            [("team_id", ASCENDING), ("priority", ASCENDING), ("updated_at", DESCENDING), ("_id", ASCENDING)],
            name="idx_item_keyset_prio_updated",
        ),
        # Attention and SLA queries
        IndexModel(
            [("team_id", ASCENDING), ("status", ASCENDING), ("attention_due_at", ASCENDING)],
            name="idx_item_status_attention",
        ),
        IndexModel([("assignee_id", ASCENDING), ("status", ASCENDING)], name="idx_item_assignee_status"),
        IndexModel([("reporter_id", ASCENDING)], name="idx_item_reporter"),
    ])

    # 6. item_events (Append-only timeline)
    await db.item_events.create_indexes([
        IndexModel([("item_id", ASCENDING), ("seq", ASCENDING)], unique=True, name="uq_item_events_item_seq"),
        IndexModel([("team_id", ASCENDING), ("created_at", DESCENDING)], name="idx_item_events_team_created"),
    ])

    # 7. approvals (At most one PENDING approval per item)
    await db.approvals.create_indexes([
        IndexModel(
            [("item_id", ASCENDING)],
            unique=True,
            partialFilterExpression={"status": "pending"},
            name="uq_approvals_single_pending",
        ),
        IndexModel([("team_id", ASCENDING), ("status", ASCENDING)], name="idx_approvals_team_status"),
    ])

    # 8. idempotency records
    await db.idempotency.create_indexes([
        IndexModel([("user_id", ASCENDING), ("key", ASCENDING)], unique=True, name="uq_idempotency_user_key"),
        IndexModel([("expires_at", ASCENDING)], expireAfterSeconds=0, name="ttl_idempotency_expiry"),
    ])

    # 9. transactional outbox
    await db.outbox.create_indexes([
        IndexModel([("status", ASCENDING), ("next_attempt_at", ASCENDING)], name="idx_outbox_poll"),
        IndexModel([("status", ASCENDING), ("lease_expires_at", ASCENDING)], name="idx_outbox_reclaim"),
    ])

    # 10. in-app notifications
    await db.notifications.create_indexes([
        IndexModel([("recipient_id", ASCENDING), ("read", ASCENDING), ("created_at", DESCENDING)], name="idx_notifications_user_read"),
        IndexModel(
            [("recipient_id", ASCENDING), ("dedupe_key", ASCENDING)],
            unique=True,
            name="uq_notifications_recipient_dedupe",
        ),
    ])

    # 11. item_chunks (RAG vector store metadata and lookup)
    await db.item_chunks.create_indexes([
        IndexModel([("item_id", ASCENDING)], name="idx_chunks_item_id"),
        IndexModel([("source_id", ASCENDING)], name="idx_chunks_source_id"),
        IndexModel([("team_id", ASCENDING)], name="idx_chunks_team_id"),
    ])

    # 12. ai_queries (Audit and evaluation)
    await db.ai_queries.create_indexes([
        IndexModel([("created_at", ASCENDING)], expireAfterSeconds=2592000, name="ttl_ai_queries_30d"),
        IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)], name="idx_ai_queries_user_created"),
    ])
