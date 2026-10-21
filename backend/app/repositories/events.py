"""
Append-only audit event repository for Opsboard work items.
Matches docs/DATA_MODEL.md §2.6.

CRITICAL INVARIANT:
This collection is strictly append-only. There are NO update or delete methods in this module.
Every event document is inserted inside the business transaction via `append_event_in_session`.
"""

from typing import Any, Dict, List, Optional
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.asynchronous.client_session import AsyncClientSession

from app.domain.enums import EventType
from app.domain.models.base import generate_id, utc_now


class EventRepository:
    def __init__(self, db: AsyncDatabase) -> None:
        self.db = db

    async def append_event_in_session(
        self,
        session: AsyncClientSession,
        item_id: str,
        team_id: str,
        seq: int,
        event_type: EventType,
        actor_id: str,
        actor_name: str,
        data: Dict[str, Any],
        *,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Append an immutable audit event to item_events inside an active transaction.
        """
        event_id = generate_id("evt")
        type_val = event_type.value if hasattr(event_type, "value") else str(event_type)
        now = utc_now()
        doc = {
            "_id": event_id,
            "item_id": item_id,
            "team_id": team_id,
            "seq": seq,
            "type": type_val,
            "actor_id": actor_id,
            "actor_name": actor_name,
            "data": data,
            "correlation_id": correlation_id,
            "created_at": now,
        }
        await self.db.item_events.insert_one(doc, session=session)
        return doc

    async def get_timeline(
        self,
        item_id: str,
        since_seq: int = 0,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve ordered timeline events for an item. Keyset paginated on seq.
        """
        query: Dict[str, Any] = {"item_id": item_id}
        if since_seq > 0:
            query["seq"] = {"$gt": since_seq}

        cursor = self.db.item_events.find(query).sort("seq", 1).limit(min(limit, 100))
        return await cursor.to_list(length=limit)

    async def get_events_since(self, item_id: str, since_seq: int) -> List[Dict[str, Any]]:
        """
        Retrieve all events since a given sequence number.
        Used by 412 VERSION_CONFLICT error responses to tell the user what changed.
        """
        cursor = self.db.item_events.find(
            {"item_id": item_id, "seq": {"$gt": since_seq}}
        ).sort("seq", 1)
        return await cursor.to_list(length=100)

    async def get_item_events(self, item_id: str) -> List[Dict[str, Any]]:
        """Retrieve all audit events for an item sorted by sequence."""
        cursor = self.db.item_events.find({"item_id": item_id}).sort("seq", 1)
        return await cursor.to_list(length=500)

    async def get_recent_events(self, limit: int = 1) -> List[Dict[str, Any]]:
        """Retrieve most recent events across the database."""
        cursor = self.db.item_events.find({}).sort("_id", -1).limit(limit)
        return await cursor.to_list(length=limit)

    async def find_since(self, filter_q: Dict[str, Any], limit: int = 20) -> List[Dict[str, Any]]:
        """Find events matching filter query sorted by _id ascending."""
        cursor = self.db.item_events.find(filter_q).sort("_id", 1).limit(limit)
        return await cursor.to_list(length=limit)
