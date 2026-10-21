"""
Comprehensive unit tests for Opsboard domain models, validations, and enums.
Uses python's standard unittest library (runnable via python -m unittest or pytest).
"""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.domain.enums import (
    ItemStatus,
    ItemPriority,
    ItemType,
    TeamRole,
    EventType,
    ApprovalStatus,
    OutboxStatus,
    ChunkKind,
)
from app.domain.models import (
    User,
    UserCreate,
    UserContext,
    Team,
    TeamCreate,
    WorkItem,
    WorkItemCreate,
    WorkItemUpdate,
    WorkItemSummary,
    ItemEvent,
    Approval,
    OutboxMessage,
    Notification,
    IdempotencyRecord,
    ItemChunk,
    calculate_attention_due_at,
)


class TestDomainEnums(unittest.TestCase):
    def test_role_hierarchy(self):
        """Verify role ordering: lead > member > viewer."""
        self.assertTrue(TeamRole.LEAD > TeamRole.MEMBER)
        self.assertTrue(TeamRole.MEMBER > TeamRole.VIEWER)
        self.assertTrue(TeamRole.LEAD >= TeamRole.LEAD)
        self.assertFalse(TeamRole.VIEWER >= TeamRole.MEMBER)
        self.assertFalse(TeamRole.MEMBER > TeamRole.LEAD)

    def test_item_statuses(self):
        """Verify active and terminal state sets."""
        self.assertIn(ItemStatus.CLOSED, ItemStatus.terminal_states())
        self.assertNotIn(ItemStatus.OPEN, ItemStatus.terminal_states())
        self.assertIn(ItemStatus.IN_PROGRESS, ItemStatus.active_states())
        self.assertNotIn(ItemStatus.CLOSED, ItemStatus.active_states())


class TestUserModel(unittest.TestCase):
    def test_user_creation_and_defaults(self):
        user = User(
            email="priya@example.com",
            name="Priya Shah",
            password_hash="argon2id$hashed",
            is_org_admin=True,
        )
        self.assertTrue(user.id.startswith("usr_"))
        self.assertEqual(user.email, "priya@example.com")
        self.assertTrue(user.is_org_admin)
        self.assertIsInstance(user.created_at, datetime)

    def test_user_context_roles(self):
        ctx = UserContext(
            user_id="usr_123",
            email="priya@example.com",
            name="Priya Shah",
            is_org_admin=False,
            team_roles={"team_ops": TeamRole.LEAD, "team_pay": TeamRole.VIEWER},
        )
        self.assertEqual(ctx.get_role("team_ops"), TeamRole.LEAD)
        self.assertEqual(ctx.get_role("team_pay"), TeamRole.VIEWER)
        self.assertIsNone(ctx.get_role("team_engineering"))
        self.assertTrue(ctx.is_member_of("team_ops"))
        self.assertFalse(ctx.is_member_of("team_engineering"))


class TestTeamModel(unittest.TestCase):
    def test_team_key_prefix_validation(self):
        team = Team(
            name="Incident Response",
            key_prefix="INC",
            description="Production operations",
        )
        self.assertTrue(team.id.startswith("team_"))
        self.assertEqual(team.key_prefix, "INC")
        self.assertEqual(team.item_counter, 0)


class TestWorkItemModel(unittest.TestCase):
    def test_work_item_defaults_and_optimistic_locking(self):
        item = WorkItem(
            team_id="team_ops",
            key="OPS-101",
            title="Database connection pool exhaustion",
            reporter_id="usr_1",
            priority=ItemPriority.P0,
        )
        self.assertTrue(item.id.startswith("itm_"))
        self.assertEqual(item.version, 1)
        self.assertEqual(item.event_seq, 0)
        self.assertEqual(item.status, ItemStatus.OPEN)
        self.assertEqual(item.priority, ItemPriority.P0)

    def test_tag_sanitization(self):
        item = WorkItem(
            team_id="team_ops",
            key="OPS-102",
            title="Update compliance check",
            reporter_id="usr_1",
            tags=["  Security ", "SECURITY", "PAYMENTS", "  infrastructure  "],
        )
        # Should lowercase and deduplicate
        self.assertEqual(item.tags, ["security", "payments", "infrastructure"])

    def test_sla_calculation(self):
        base_time = datetime(2026, 10, 20, 12, 0, 0, tzinfo=timezone.utc)
        
        # P0 SLA is 1 hour
        p0_due = calculate_attention_due_at(ItemPriority.P0, ItemStatus.OPEN, base_time)
        self.assertEqual(p0_due, base_time + timedelta(hours=1))

        # P1 SLA is 4 hours
        p1_due = calculate_attention_due_at(ItemPriority.P1, ItemStatus.OPEN, base_time)
        self.assertEqual(p1_due, base_time + timedelta(hours=4))

        # P2 SLA is 24 hours
        p2_due = calculate_attention_due_at(ItemPriority.P2, ItemStatus.OPEN, base_time)
        self.assertEqual(p2_due, base_time + timedelta(hours=24))

        # P3 SLA is 72 hours
        p3_due = calculate_attention_due_at(ItemPriority.P3, ItemStatus.OPEN, base_time)
        self.assertEqual(p3_due, base_time + timedelta(hours=72))

        # Blocked status caps window at 24 hours even for P3
        blocked_due = calculate_attention_due_at(ItemPriority.P3, ItemStatus.BLOCKED, base_time)
        self.assertEqual(blocked_due, base_time + timedelta(hours=24))

    def test_work_item_summary_projection(self):
        summary = WorkItemSummary(
            id="itm_1",
            team_id="team_ops",
            key="OPS-1",
            title="Summary test",
            type=ItemType.ISSUE,
            status=ItemStatus.OPEN,
            priority=ItemPriority.P2,
            reporter_id="usr_1",
            last_activity_at=datetime.now(timezone.utc),
            attention_due_at=datetime.now(timezone.utc),
            tags=["ops"],
            version=1,
        )
        self.assertEqual(summary.key, "OPS-1")


class TestAuditAndConcurrencyModels(unittest.TestCase):
    def test_item_event(self):
        event = ItemEvent(
            item_id="itm_1",
            team_id="team_ops",
            seq=1,
            type=EventType.ITEM_CLAIMED,
            actor_id="usr_2",
            actor_name="Alex Kim",
            data={"action": "claimed"},
        )
        self.assertTrue(event.id.startswith("evt_"))
        self.assertEqual(event.seq, 1)

    def test_outbox_message(self):
        msg = OutboxMessage(
            type="notify",
            payload={"event_id": "evt_1", "item_key": "OPS-10"},
        )
        self.assertTrue(msg.id.startswith("out_"))
        self.assertEqual(msg.status, OutboxStatus.PENDING)
        self.assertEqual(msg.attempts, 0)
        self.assertEqual(msg.max_attempts, 6)

    def test_idempotency_record(self):
        record = IdempotencyRecord(
            user_id="usr_1",
            key="client-uuid-999",
            request_hash="sha256_mock_hash",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        self.assertTrue(record.id.startswith("idem_"))
        self.assertEqual(record.key, "client-uuid-999")

    def test_vector_item_chunk(self):
        chunk = ItemChunk(
            _id="itm_123:0",
            team_id="team_ops",
            item_id="itm_123",
            item_key="OPS-123",
            kind=ChunkKind.ITEM,
            source_id="itm_123",
            text="[OPS-123] Database latency spike",
            text_hash="abc123hash",
            embedding=[0.1] * 384,
            content_version=1,
        )
        self.assertEqual(chunk.id, "itm_123:0")
        self.assertEqual(len(chunk.embedding), 384)
        self.assertEqual(chunk.kind, ChunkKind.ITEM)


if __name__ == "__main__":
    unittest.main()
