"""
Background Outbox Worker process for Opsboard.
Continuously polls the transactional outbox, claims jobs using atomic leases,
executes handlers idempotently, and manages exponential backoff and dead-lettering.
Matches docs/SYSTEM_DESIGN.md §6.4.
"""

import asyncio
import logging
import os
import signal
import uuid
from typing import Any, Dict

from app.core.config import get_settings
from app.db.client import mongo_manager
from app.domain.enums import OutboxType
from app.infra.outbox import OutboxService
from app.repositories.notifications import NotificationRepository
from app.repositories.teams import TeamRepository

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("opsboard.worker")


class OutboxWorker:
    def __init__(self) -> None:
        self.worker_id = f"worker-{uuid.uuid4().hex[:8]}"
        self.running = False
        self.settings = get_settings()

    async def start(self) -> None:
        """Start worker loop and initialize DB connection."""
        self.running = True
        logger.info("Starting outbox worker [%s]...", self.worker_id)
        await mongo_manager.connect()
        db = mongo_manager.get_database()

        poll_interval = self.settings.WORKER_POLL_INTERVAL_MS / 1000.0

        while self.running:
            try:
                job = await OutboxService.claim_next_job(
                    db,
                    self.worker_id,
                    lease_seconds=self.settings.OUTBOX_LEASE_SECONDS,
                )
                if job:
                    await self.process_job(db, job)
                else:
                    await asyncio.sleep(poll_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in worker main loop: %s", e)
                await asyncio.sleep(poll_interval)

        await mongo_manager.close()
        logger.info("Outbox worker [%s] stopped cleanly.", self.worker_id)

    async def stop(self) -> None:
        self.running = False

    async def process_job(self, db, job: Dict[str, Any]) -> None:
        job_id = job["_id"]
        job_type = job["type"]
        payload = job.get("payload", {})
        attempts = job.get("attempts", 1)
        max_attempts = job.get("max_attempts", self.settings.OUTBOX_MAX_ATTEMPTS)

        logger.info("Processing job %s [type=%s, attempt=%d/%d]...", job_id, job_type, attempts, max_attempts)

        try:
            if job_type == OutboxType.NOTIFY.value or job_type == "notify":
                await self.handle_notify(db, payload)
            elif job_type == OutboxType.INDEX_ITEM.value or job_type == "index_item":
                await self.handle_index_item(db, payload)
            else:
                logger.warning("Unknown job type: %s, skipping...", job_type)

            await OutboxService.mark_completed(db, job_id)
            logger.info("Job %s completed successfully.", job_id)
        except Exception as e:
            logger.exception("Job %s failed: %s", job_id, e)
            await OutboxService.mark_failed(
                db,
                job_id,
                error_message=str(e),
                current_attempts=attempts,
                max_attempts=max_attempts,
            )

    async def handle_notify(self, db, payload: Dict[str, Any]) -> None:
        """
        Dispatches notifications to recipients idempotently using dedupe_key.
        """
        item_id = payload.get("item_id", "")
        team_id = payload.get("team_id", "")
        event_type = payload.get("event_type", "")
        title = payload.get("title", "Opsboard Notification")
        recipients = list(payload.get("recipient_user_ids", []))

        # If approval requested and recipients empty, fan out to team leads
        if event_type == "approval_requested" and not recipients:
            team_repo = TeamRepository(db)
            members = await team_repo.get_team_members(team_id)
            recipients = [m["user_id"] for m in members if m["role"] == "lead"]

        notif_repo = NotificationRepository(db)
        for recipient_id in set(recipients):
            dedupe_key = f"{item_id}:{event_type}:{recipient_id}"
            await notif_repo.create_notification_idempotent(
                recipient_id=recipient_id,
                team_id=team_id,
                item_id=item_id,
                event_id=payload.get("event_id", ""),
                title=title,
                body=payload.get("body", title),
                dedupe_key=dedupe_key,
            )
            # Simulated email dispatch per KNOWN_LIMITATIONS.md §1
            logger.info("[EMAIL LOG] Delivered notification '%s' to user %s via log channel.", title, recipient_id)

    async def handle_index_item(self, db, payload: Dict[str, Any]) -> None:
        """
        Asynchronously creates search / vector chunks for RAG.
        Deterministic chunking ensures idempotency.
        """
        item_id = payload.get("item_id")
        content_version = payload.get("content_version", 1)
        if item_id:
            from app.services.ai_service import AIService
            ai_service = AIService(db)
            chunks_indexed = await ai_service.index_item(item_id)
            logger.info("[INDEXER] Indexed %d chunk(s) (content_version=%d) for item %s.", chunks_indexed, content_version, item_id)
        else:
            logger.warning("[INDEXER] Missing item_id in index_item payload.")


async def main():
    worker = OutboxWorker()
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda: asyncio.create_task(worker.stop()))
        except NotImplementedError:
            pass  # Windows compatibility

    await worker.start()


if __name__ == "__main__":
    asyncio.run(main())
