"""
In-app notifications repository.
Enforces deduplication per recipient and provides paginated notification lists.
Matches docs/DATA_MODEL.md §2.9.
"""

from typing import Any, Dict, List, Optional
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.domain.models.base import generate_id, utc_now


class NotificationRepository:
    def __init__(self, db: AsyncDatabase) -> None:
        self.db = db

    async def create_notification_idempotent(
        self,
        recipient_id: str,
        team_id: str,
        item_id: str,
        event_id: str,
        title: str,
        body: str,
        dedupe_key: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Idempotent notification creation.
        If a duplicate (recipient_id, dedupe_key) arrives, it is safely ignored.
        """
        notif_id = generate_id("notif")
        doc = {
            "_id": notif_id,
            "recipient_id": recipient_id,
            "team_id": team_id,
            "item_id": item_id,
            "event_id": event_id,
            "title": title,
            "body": body,
            "dedupe_key": dedupe_key,
            "read": False,
            "created_at": utc_now(),
        }
        try:
            await self.db.notifications.insert_one(doc)
            return doc
        except DuplicateKeyError:
            # Already created by a previous attempt of the outbox worker
            return None

    async def list_for_user(
        self,
        user_id: str,
        unread_only: bool = False,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        query: Dict[str, Any] = {"recipient_id": user_id}
        if unread_only:
            query["read"] = False

        cursor = self.db.notifications.find(query).sort("created_at", -1).limit(min(limit, 100))
        return await cursor.to_list(length=limit)

    async def mark_as_read(self, notification_id: str, user_id: str) -> None:
        await self.db.notifications.update_one(
            {"_id": notification_id, "recipient_id": user_id},
            {"$set": {"read": True}},
        )

    async def mark_all_as_read(self, user_id: str) -> None:
        await self.db.notifications.update_many(
            {"recipient_id": user_id, "read": False},
            {"$set": {"read": True}},
        )
