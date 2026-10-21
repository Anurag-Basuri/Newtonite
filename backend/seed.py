"""
Seed script for Opsboard.
Populates realistic demo accounts, multi-team memberships, and items across all
6 categories from the Newtonite Software Engineering Challenge brief.
"""

import asyncio
from datetime import timedelta
import logging

from app.core.config import get_settings
from app.db.client import mongo_manager
from app.db.indexes import ensure_indexes
from app.domain.attention import calculate_attention_due_at
from app.domain.enums import ItemPriority, ItemResolution, ItemStatus, ItemType, TeamRole
from app.domain.models.base import generate_id, utc_now
from app.repositories.users import UserRepository

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("opsboard.seed")


async def seed():
    logger.info("Connecting to MongoDB...")
    await mongo_manager.connect()
    db = mongo_manager.get_database()

    logger.info("Ensuring indexes...")
    await ensure_indexes(db)

    # 1. Clear existing seed data if needed
    logger.info("Resetting collections for clean demonstration...")
    for coll in ["users", "sessions", "teams", "memberships", "work_items", "item_events", "approvals", "idempotency", "outbox", "notifications", "item_chunks", "ai_queries"]:
        await db[coll].delete_many({})

    user_repo = UserRepository(db)
    pwd = "Password123!"

    # 2. Seed Users
    logger.info("Creating demo users...")
    admin_user = await user_repo.create_user("Alice Admin", "admin@opsboard.dev", pwd, is_org_admin=True)
    lead_user = await user_repo.create_user("Priya Lead", "lead@opsboard.dev", pwd)
    member1 = await user_repo.create_user("Marcus Member", "member@opsboard.dev", pwd)
    member2 = await user_repo.create_user("Sarah Contender", "member2@opsboard.dev", pwd)
    viewer_user = await user_repo.create_user("Victor Viewer", "viewer@opsboard.dev", pwd)

    # 3. Seed Teams
    logger.info("Creating demo teams...")
    now = utc_now()
    teams = [
        {"_id": generate_id("team"), "name": "Payments Operations", "slug": "payments", "key_prefix": "PAY", "item_counter": 103, "created_at": now, "updated_at": now},
        {"_id": generate_id("team"), "name": "Core Engineering", "slug": "engineering", "key_prefix": "ENG", "item_counter": 201, "created_at": now, "updated_at": now},
        {"_id": generate_id("team"), "name": "Compliance & Risk", "slug": "compliance", "key_prefix": "CMP", "item_counter": 50, "created_at": now, "updated_at": now},
    ]
    await db.teams.insert_many(teams)
    pay_team, eng_team, cmp_team = teams[0], teams[1], teams[2]

    # 4. Seed Memberships
    logger.info("Creating multi-team memberships...")
    memberships = [
        # Payments Team
        {"_id": generate_id("mem"), "team_id": pay_team["_id"], "user_id": lead_user["_id"], "role": TeamRole.LEAD.value, "created_at": now},
        {"_id": generate_id("mem"), "team_id": pay_team["_id"], "user_id": member1["_id"], "role": TeamRole.MEMBER.value, "created_at": now},
        {"_id": generate_id("mem"), "team_id": pay_team["_id"], "user_id": member2["_id"], "role": TeamRole.MEMBER.value, "created_at": now},
        {"_id": generate_id("mem"), "team_id": pay_team["_id"], "user_id": viewer_user["_id"], "role": TeamRole.VIEWER.value, "created_at": now},

        # Engineering Team
        {"_id": generate_id("mem"), "team_id": eng_team["_id"], "user_id": lead_user["_id"], "role": TeamRole.MEMBER.value, "created_at": now},
        {"_id": generate_id("mem"), "team_id": eng_team["_id"], "user_id": member1["_id"], "role": TeamRole.LEAD.value, "created_at": now},

        # Compliance Team
        {"_id": generate_id("mem"), "team_id": cmp_team["_id"], "user_id": lead_user["_id"], "role": TeamRole.LEAD.value, "created_at": now},
    ]
    await db.memberships.insert_many(memberships)

    # 5. Seed Work Items & Timeline Events
    logger.info("Creating realistic operational work items across the 6 challenge categories...")
    
    # Item 1: Unassigned Urgent Item (PERFECT FOR CLAIM RACE DEMO!)
    item1_id = generate_id("itm")
    item1 = {
        "_id": item1_id,
        "team_id": pay_team["_id"],
        "key": "PAY-101",
        "title": "Double charge on checkout for customer #88192",
        "description": "Customer was debited twice during card processing spike. Payment gateway transaction IDs: txn_99182a and txn_99182b.",
        "type": ItemType.PAYMENT.value,
        "priority": ItemPriority.P1.value,
        "status": ItemStatus.OPEN.value,
        "resolution": None,
        "duplicate_of": None,
        "reporter_id": member1["_id"],
        "assignee_id": None,  # Ready to claim!
        "assigned_at": None,
        "due_at": now + timedelta(hours=3),
        "tags": ["refund", "billing", "urgent"],
        "version": 1,
        "event_seq": 1,
        "created_at": now - timedelta(minutes=45),
        "updated_at": now - timedelta(minutes=45),
        "last_activity_at": now - timedelta(minutes=45),
        "attention_due_at": calculate_attention_due_at(ItemPriority.P1, ItemStatus.OPEN, now - timedelta(minutes=45)),
        "pending_approval_id": None,
    }

    # Item 2: Item in PENDING_APPROVAL (PERFECT FOR FOUR-EYES RULE DEMO!)
    item2_id = generate_id("itm")
    apr2_id = generate_id("apr")
    item2 = {
        "_id": item2_id,
        "team_id": pay_team["_id"],
        "key": "PAY-102",
        "title": "$15,000 refund request for enterprise SLA credit",
        "description": "Enterprise customer Acme Corp requesting contract refund due to Q3 downtime window.",
        "type": ItemType.COMPLIANCE.value,
        "priority": ItemPriority.P0.value,
        "status": ItemStatus.PENDING_APPROVAL.value,
        "resolution": None,
        "duplicate_of": None,
        "reporter_id": member1["_id"],
        "assignee_id": member1["_id"],
        "assigned_at": now - timedelta(hours=2),
        "due_at": now + timedelta(hours=1),
        "tags": ["refund", "enterprise", "approval"],
        "version": 2,
        "event_seq": 2,
        "created_at": now - timedelta(hours=2),
        "updated_at": now - timedelta(minutes=30),
        "last_activity_at": now - timedelta(minutes=30),
        "attention_due_at": calculate_attention_due_at(ItemPriority.P0, ItemStatus.PENDING_APPROVAL, now - timedelta(minutes=30)),
        "pending_approval_id": apr2_id,
    }
    approval2 = {
        "_id": apr2_id,
        "item_id": item2_id,
        "team_id": pay_team["_id"],
        "status": "pending",
        "requested_by": member1["_id"],
        "requested_at": now - timedelta(minutes=30),
        "request_note": "Verified SLA downtime logs. Total credit exceeds $10k threshold; requires lead four-eyes approval.",
        "decided_by": None,
        "decided_at": None,
        "decision_reason": None,
        "created_at": now - timedelta(minutes=30),
        "updated_at": now - timedelta(minutes=30),
    }

    # Item 3: Stale / Blocked Item (Demonstrates Overview dashboard buckets)
    item3_id = generate_id("itm")
    item3 = {
        "_id": item3_id,
        "team_id": eng_team["_id"],
        "key": "ENG-201",
        "title": "Redis connection pool exhaustion during batch export",
        "description": "Nightly batch worker leaked redis pool connections causing latency spikes on primary API nodes.",
        "type": ItemType.INCIDENT.value,
        "priority": ItemPriority.P0.value,
        "status": ItemStatus.BLOCKED.value,
        "blocked_reason": "Waiting on infrastructure team to increase max client connections in VPC.",
        "resolution": None,
        "duplicate_of": None,
        "reporter_id": lead_user["_id"],
        "assignee_id": member1["_id"],
        "assigned_at": now - timedelta(days=2),
        "due_at": now - timedelta(hours=6),  # Overdue!
        "tags": ["outage", "infra", "redis"],
        "version": 3,
        "event_seq": 3,
        "created_at": now - timedelta(days=2),
        "updated_at": now - timedelta(hours=30),
        "last_activity_at": now - timedelta(hours=30),
        "attention_due_at": now - timedelta(hours=10),  # Stale!
        "pending_approval_id": None,
    }

    # Item 4: Customer Issue (General resolution flow)
    item4_id = generate_id("itm")
    item4 = {
        "_id": item4_id,
        "team_id": pay_team["_id"],
        "key": "PAY-103",
        "title": "Merchant webhook signature mismatch on payload callback",
        "description": "Merchant 4492 reporting intermittent 401 webhook signature validation failures.",
        "type": ItemType.CUSTOMER_ISSUE.value,
        "priority": ItemPriority.P2.value,
        "status": ItemStatus.IN_PROGRESS.value,
        "resolution": None,
        "duplicate_of": None,
        "reporter_id": member2["_id"],
        "assignee_id": member2["_id"],
        "assigned_at": now - timedelta(hours=5),
        "due_at": now + timedelta(hours=18),
        "tags": ["webhooks", "integration"],
        "version": 2,
        "event_seq": 2,
        "created_at": now - timedelta(hours=5),
        "updated_at": now - timedelta(hours=1),
        "last_activity_at": now - timedelta(hours=1),
        "attention_due_at": calculate_attention_due_at(ItemPriority.P2, ItemStatus.IN_PROGRESS, now - timedelta(hours=1)),
        "pending_approval_id": None,
    }

    await db.work_items.insert_many([item1, item2, item3, item4])
    await db.approvals.insert_one(approval2)

    # Initial Audit Events
    events = [
        {"_id": generate_id("evt"), "item_id": item1_id, "team_id": pay_team["_id"], "seq": 1, "type": "item.created", "actor_id": member1["_id"], "actor_name": "Marcus Member", "data": {"title": item1["title"]}, "created_at": now - timedelta(minutes=45)},
        {"_id": generate_id("evt"), "item_id": item2_id, "team_id": pay_team["_id"], "seq": 1, "type": "item.created", "actor_id": member1["_id"], "actor_name": "Marcus Member", "data": {"title": item2["title"]}, "created_at": now - timedelta(hours=2)},
        {"_id": generate_id("evt"), "item_id": item2_id, "team_id": pay_team["_id"], "seq": 2, "type": "approval.requested", "actor_id": member1["_id"], "actor_name": "Marcus Member", "data": {"request_note": approval2["request_note"]}, "created_at": now - timedelta(minutes=30)},
        {"_id": generate_id("evt"), "item_id": item3_id, "team_id": eng_team["_id"], "seq": 1, "type": "item.created", "actor_id": lead_user["_id"], "actor_name": "Priya Lead", "data": {"title": item3["title"]}, "created_at": now - timedelta(days=2)},
        {"_id": generate_id("evt"), "item_id": item3_id, "team_id": eng_team["_id"], "seq": 2, "type": "item.assigned", "actor_id": lead_user["_id"], "actor_name": "Priya Lead", "data": {"assignee_id": member1["_id"], "action": "assigned"}, "created_at": now - timedelta(days=2)},
        {"_id": generate_id("evt"), "item_id": item3_id, "team_id": eng_team["_id"], "seq": 3, "type": "item.transitioned", "actor_id": member1["_id"], "actor_name": "Marcus Member", "data": {"from_status": "in_progress", "to_status": "blocked", "reason": item3["blocked_reason"]}, "created_at": now - timedelta(hours=30)},
    ]
    await db.item_events.insert_many(events)

    logger.info("Successfully seeded database with demo users, teams, and sample items!")
    logger.info("Demo Accounts Created:")
    logger.info("  1. Priya Lead    - lead@opsboard.dev    / Password123! (Lead in Payments & Infrastructure)")
    logger.info("  2. Marcus Member - member@opsboard.dev  / Password123! (Member in Payments, Lead in Eng)")
    logger.info("  3. Sarah Member  - member2@opsboard.dev / Password123! (Member in Payments, ready for claim race)")
    logger.info("  4. Victor Viewer - viewer@opsboard.dev  / Password123! (Viewer in Payments)")
    logger.info("  5. Alice Admin   - admin@opsboard.dev   / Password123! (Org Admin)")

    await mongo_manager.close()


if __name__ == "__main__":
    asyncio.run(seed())
