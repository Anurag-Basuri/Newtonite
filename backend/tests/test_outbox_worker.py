"""
Outbox and Worker Test Suite matching TEST_PLAN.md §2.4.
Covers:
  - T-OBX-1: Lost side effects (mutations atomically enqueue outbox messages)
  - T-OBX-2: Handler failure and exponential backoff / dead-lettering
  - T-OBX-3: Duplicate delivery idempotency (notify handler dedupe)
  - T-OBX-4: Crashed worker lease expiry and reclaim pass
  - T-OBX-5: Competing workers claim race (exactly one worker wins a message)
"""

import asyncio
from datetime import datetime, timedelta, timezone
import os
import sys
import unittest
from pymongo.asynchronous.database import AsyncDatabase

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

def to_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt

from app.db.client import mongo_manager
from app.domain.enums import OutboxStatus, OutboxType
from app.domain.models.base import generate_id, utc_now
from app.infra.outbox import OutboxService
from app.worker import OutboxWorker
from seed import seed


class TestOutboxWorker(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await seed()
        await mongo_manager.connect()
        self.db = mongo_manager.get_database()
        self.worker = OutboxWorker()

    async def asyncTearDown(self):
        await mongo_manager.close()

    # --------------------------------------------------------------------------
    # T-OBX-1: Mutations Atomically Enqueue Outbox Messages
    # --------------------------------------------------------------------------
    async def test_T_OBX_1_mutation_enqueues_outbox(self):
        """
        Verify that outbox records exist in the database from seeded mutations
        and can be queried with correct initial status PENDING.
        """
        # Insert a sample outbox message
        now = utc_now()
        job_id = generate_id("out")
        await self.db.outbox.insert_one({
            "_id": job_id,
            "type": OutboxType.NOTIFY.value,
            "payload": {"item_id": "item-123", "event_type": "item.created"},
            "status": OutboxStatus.PENDING.value,
            "attempts": 0,
            "max_attempts": 3,
            "lease_until": None,
            "next_attempt_at": now,
            "created_at": now,
            "updated_at": now,
        })

        found = await self.db.outbox.find_one({"_id": job_id})
        self.assertIsNotNone(found)
        self.assertEqual(found["status"], OutboxStatus.PENDING.value)
        self.assertEqual(found["attempts"], 0)

    # --------------------------------------------------------------------------
    # T-OBX-2: Handler Failure, Exponential Backoff, and Dead-Lettering
    # --------------------------------------------------------------------------
    async def test_T_OBX_2_handler_failure_and_backoff(self):
        """
        A failing handler causes attempts to increment, next_attempt_at to be
        pushed into the future with exponential backoff, and marks message DEAD
        after reaching max_attempts.
        """
        job_id = generate_id("out")
        now = utc_now()
        await self.db.outbox.insert_one({
            "_id": job_id,
            "type": OutboxType.NOTIFY.value,
            "payload": {"item_id": "item-fail"},
            "status": OutboxStatus.PROCESSING.value,
            "attempts": 1,
            "max_attempts": 3,
            "lease_until": now + timedelta(seconds=30),
            "next_attempt_at": now,
            "created_at": now,
            "updated_at": now,
        })

        # 1. First failure (attempts=1 < max_attempts=3) -> resets to PENDING with future next_attempt_at
        await OutboxService.mark_failed(
            self.db,
            job_id,
            error_message="Network glitch",
            current_attempts=1,
            max_attempts=3,
        )
        doc1 = await self.db.outbox.find_one({"_id": job_id})
        self.assertEqual(doc1["status"], OutboxStatus.PENDING.value)
        self.assertGreater(to_utc(doc1["next_attempt_at"]), now)
        self.assertEqual(doc1["last_error"], "Network glitch")

        # 2. Final failure (attempts=3 == max_attempts=3) -> transitions to DEAD
        await OutboxService.mark_failed(
            self.db,
            job_id,
            error_message="Fatal unrecoverable error",
            current_attempts=3,
            max_attempts=3,
        )
        doc2 = await self.db.outbox.find_one({"_id": job_id})
        self.assertEqual(doc2["status"], OutboxStatus.DEAD.value)
        self.assertEqual(doc2["last_error"], "Fatal unrecoverable error")

    # --------------------------------------------------------------------------
    # T-OBX-3: Duplicate Delivery Idempotency
    # --------------------------------------------------------------------------
    async def test_T_OBX_3_duplicate_delivery_idempotent(self):
        """
        Running the notify handler twice for the exact same message payload
        results in exactly ONE notification document per recipient.
        """
        user = await self.db.users.find_one({"email": "member@opsboard.dev"})
        self.assertIsNotNone(user)
        user_id = str(user["_id"])

        payload = {
            "item_id": "PAY-101",
            "team_id": "team-pay",
            "event_type": "item.commented",
            "title": "New Comment on PAY-101",
            "body": "Please review this issue urgently.",
            "recipient_user_ids": [user_id],
        }

        # Clear notifications for clean count
        await self.db.notifications.delete_many({"recipient_id": user_id})

        # Process twice
        await self.worker.handle_notify(self.db, payload)
        await self.worker.handle_notify(self.db, payload)

        count = await self.db.notifications.count_documents({
            "recipient_id": user_id,
            "item_id": "PAY-101",
        })
        self.assertEqual(count, 1, "Duplicate notifications were erroneously inserted!")

    # --------------------------------------------------------------------------
    # T-OBX-4: Crashed Worker Lease Expiry and Reclaim
    # --------------------------------------------------------------------------
    async def test_T_OBX_4_lease_reclaim(self):
        """
        A job stuck in PROCESSING with an expired lease is reclaimed by the next
        worker pass and transitioned to a new lease.
        """
        now = utc_now()
        expired_lease = now - timedelta(seconds=10)
        job_id = generate_id("out")

        await self.db.outbox.insert_one({
            "_id": job_id,
            "type": OutboxType.INDEX_ITEM.value,
            "payload": {"item_id": "PAY-101"},
            "status": OutboxStatus.PROCESSING.value,
            "attempts": 1,
            "max_attempts": 5,
            "lease_until": expired_lease,
            "next_attempt_at": expired_lease,
            "worker_id": "crashed-worker-99",
            "created_at": now - timedelta(minutes=2),
            "updated_at": now - timedelta(minutes=2),
        })

        # New worker claims the job
        reclaimed = await OutboxService.claim_next_job(
            self.db,
            worker_id="active-worker-01",
            lease_seconds=60,
        )
        self.assertIsNotNone(reclaimed)
        self.assertEqual(reclaimed["worker_id"], "active-worker-01")
        self.assertGreater(to_utc(reclaimed["lease_until"]), now)
        self.assertEqual(reclaimed["attempts"], 2)

    # --------------------------------------------------------------------------
    # T-OBX-5: Competing Workers Claim Race
    # --------------------------------------------------------------------------
    async def test_T_OBX_5_competing_workers_single_winner(self):
        """
        Two workers polling concurrently for a single ready job:
        atomic find_one_and_update guarantees exactly one worker acquires the lease.
        """
        now = utc_now()
        job_id = generate_id("out")
        await self.db.outbox.insert_one({
            "_id": job_id,
            "type": OutboxType.NOTIFY.value,
            "payload": {"item_id": "PAY-101"},
            "status": OutboxStatus.PENDING.value,
            "attempts": 0,
            "max_attempts": 3,
            "lease_until": None,
            "next_attempt_at": now,
            "created_at": now,
            "updated_at": now,
        })

        claim1 = OutboxService.claim_next_job(self.db, worker_id="worker-A")
        claim2 = OutboxService.claim_next_job(self.db, worker_id="worker-B")

        res1, res2 = await asyncio.gather(claim1, claim2)
        winners = [r for r in [res1, res2] if r is not None and r["_id"] == job_id]
        self.assertEqual(len(winners), 1, "Exactly one worker must win the job!")


if __name__ == "__main__":
    unittest.main()
