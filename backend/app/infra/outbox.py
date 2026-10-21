"""
Transactional Outbox infrastructure for asynchronous workers.
Implements atomic job claiming with leases, exponential backoff, and dead-lettering.

CRITICAL INVARIANTS:
1. `enqueue_in_session` MUST be called inside the active UnitOfWork session
   together with the item state mutation and audit event document.
2. `claim_job` uses atomic conditional find_one_and_update to guarantee that
   competing workers never process the same message concurrently.
3. Expired worker leases are automatically reclaimed.
4. Failed jobs transition to DEAD after max_attempts to preserve system health.
"""

from datetime import datetime, timedelta
import random
from typing import Any, Dict, Optional
from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.asynchronous.client_session import AsyncClientSession

from app.domain.enums import OutboxStatus, OutboxType
from app.domain.models.base import generate_id, utc_now


class OutboxService:
    """Manages outbox persistence, worker leases, and retry lifecycles."""

    @staticmethod
    async def enqueue_in_session(
        session: AsyncClientSession,
        db: AsyncDatabase,
        outbox_type: OutboxType,
        payload: Dict[str, Any],
        *,
        correlation_id: Optional[str] = None,
        max_attempts: int = 6,
    ) -> str:
        """
        Enqueue an outbox message inside the caller's atomic transaction session.
        """
        now = utc_now()
        message_id = generate_id("out")
        doc = {
            "_id": message_id,
            "type": outbox_type.value if hasattr(outbox_type, "value") else str(outbox_type),
            "payload": payload,
            "status": OutboxStatus.PENDING.value,
            "attempts": 0,
            "max_attempts": max_attempts,
            "lease_until": None,
            "last_error": None,
            "next_attempt_at": now,
            "correlation_id": correlation_id,
            "created_at": now,
            "updated_at": now,
        }
        await db.outbox.insert_one(doc, session=session)
        return message_id

    @staticmethod
    async def claim_next_job(
        db: AsyncDatabase,
        worker_id: str,
        lease_seconds: int = 30,
    ) -> Optional[Dict[str, Any]]:
        """
        Atomically find and lease the next available outbox job.
        Handles both new pending jobs and expired leases from crashed workers.
        """
        now = utc_now()
        lease_expiration = now + timedelta(seconds=lease_seconds)

        # Precondition filter:
        # Either PENDING and ready, or PROCESSING whose lease has expired
        query = {
            "$or": [
                {
                    "status": OutboxStatus.PENDING.value,
                    "next_attempt_at": {"$lte": now},
                    "lease_until": None,
                },
                {
                    "status": OutboxStatus.PROCESSING.value,
                    "lease_until": {"$lte": now},
                },
            ]
        }
        update = {
            "$set": {
                "status": OutboxStatus.PROCESSING.value,
                "lease_until": lease_expiration,
                "worker_id": worker_id,
                "updated_at": now,
            },
            "$inc": {"attempts": 1},
        }

        job = await db.outbox.find_one_and_update(
            query,
            update,
            sort=[("next_attempt_at", 1)],
            return_document=ReturnDocument.AFTER,
        )
        return job

    @staticmethod
    async def mark_completed(db: AsyncDatabase, job_id: str) -> None:
        """Mark an outbox job as successfully processed."""
        now = utc_now()
        await db.outbox.update_one(
            {"_id": job_id},
            {
                "$set": {
                    "status": OutboxStatus.COMPLETED.value,
                    "lease_until": None,
                    "updated_at": now,
                }
            },
        )

    @staticmethod
    async def mark_failed(
        db: AsyncDatabase,
        job_id: str,
        error_message: str,
        current_attempts: int,
        max_attempts: int = 6,
    ) -> None:
        """
        Record job failure with exponential backoff and jitter, or transition to DEAD.
        """
        now = utc_now()
        if current_attempts >= max_attempts:
            status = OutboxStatus.DEAD.value
            next_attempt = now
        else:
            status = OutboxStatus.PENDING.value
            # Exponential backoff with jitter: 2^attempts seconds + up to 1000ms jitter, capped at 300s
            backoff_base = min(300, 2 ** min(current_attempts, 8))
            jitter = random.uniform(0.1, 1.0)
            next_attempt = now + timedelta(seconds=backoff_base + jitter)

        await db.outbox.update_one(
            {"_id": job_id},
            {
                "$set": {
                    "status": status,
                    "last_error": error_message[:1000],
                    "next_attempt_at": next_attempt,
                    "lease_until": None,
                    "updated_at": now,
                }
            },
        )
