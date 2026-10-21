"""
Work items data access repository with atomic conditional updates.
Matches docs/DATA_MODEL.md §2.5 and implements all critical concurrency primitives.

CRITICAL INVARIANTS:
1. `claim_item` uses conditional find_one_and_update with `assignee_id: None` in the filter.
   Never check-then-write for claiming.
2. `update_with_version` uses conditional find_one_and_update with `version: expected_version`.
   Stale edits fail atomically at the database level.
3. List queries use keyset pagination and explicit projections. No skip().
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from pymongo import ReturnDocument, DESCENDING, ASCENDING
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.asynchronous.client_session import AsyncClientSession

from app.core.errors import AlreadyClaimedError, PreconditionFailedError
from app.domain.enums import ItemStatus, ItemPriority
from app.domain.models.base import utc_now


ITEM_SUMMARY_PROJECTION = {
    "_id": 1,
    "key": 1,
    "team_id": 1,
    "title": 1,
    "type": 1,
    "priority": 1,
    "status": 1,
    "resolution": 1,
    "duplicate_of": 1,
    "reporter_id": 1,
    "assignee_id": 1,
    "assigned_at": 1,
    "due_at": 1,
    "tags": 1,
    "version": 1,
    "event_seq": 1,
    "created_at": 1,
    "updated_at": 1,
    "last_activity_at": 1,
    "attention_due_at": 1,
    "pending_approval_id": 1,
}


class ItemRepository:
    def __init__(self, db: AsyncDatabase) -> None:
        self.db = db

    async def get_by_id_or_key(self, identifier: str) -> Optional[Dict[str, Any]]:
        """Look up by ObjectId string or human key (e.g. PAY-143)."""
        return await self.db.work_items.find_one({
            "$or": [{"_id": identifier}, {"key": identifier}]
        })

    async def get_by_id(self, item_id: str) -> Optional[Dict[str, Any]]:
        """Look up by primary ID."""
        return await self.get_by_id_or_key(item_id)

    async def create_item_in_session(
        self,
        session: AsyncClientSession,
        item_doc: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Insert work item document inside transaction."""
        await self.db.work_items.insert_one(item_doc, session=session)
        return item_doc

    async def claim_item_cas(
        self,
        session: AsyncClientSession,
        item_id: str,
        user_id: str,
    ) -> Dict[str, Any]:
        """
        ATOMIC COMPARE-AND-SET:
        Claim an unassigned item. The precondition `assignee_id: None` is in the filter.
        If another user claims it simultaneously, this returns None and we raise AlreadyClaimedError.
        """
        now = utc_now()
        updated = await self.db.work_items.find_one_and_update(
            {"_id": item_id, "assignee_id": None},
            {
                "$set": {
                    "assignee_id": user_id,
                    "assigned_at": now,
                    "last_activity_at": now,
                    "updated_at": now,
                },
                "$inc": {"version": 1, "event_seq": 1},
            },
            return_document=ReturnDocument.AFTER,
            session=session,
        )
        if updated:
            return updated

        # Claim failed: check who already holds it
        current = await self.db.work_items.find_one({"_id": item_id}, session=session)
        if not current:
            raise ValueError(f"Item {item_id} not found.")
        winner_id = current.get("assignee_id")
        raise AlreadyClaimedError(current_assignee_id=winner_id)

    async def release_item_cas(
        self,
        session: AsyncClientSession,
        item_id: str,
        user_id: str,
    ) -> Dict[str, Any]:
        """
        ATOMIC CONDITIONAL UPDATE:
        Release an item currently assigned to user_id.
        """
        now = utc_now()
        updated = await self.db.work_items.find_one_and_update(
            {"_id": item_id, "assignee_id": user_id},
            {
                "$set": {
                    "assignee_id": None,
                    "assigned_at": None,
                    "last_activity_at": now,
                    "updated_at": now,
                },
                "$inc": {"version": 1, "event_seq": 1},
            },
            return_document=ReturnDocument.AFTER,
            session=session,
        )
        if not updated:
            raise ValueError("Item is not assigned to you or does not exist.")
        return updated

    async def update_with_version_cas(
        self,
        session: AsyncClientSession,
        item_id: str,
        expected_version: int,
        fields_to_set: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        OPTIMISTIC CONCURRENCY CONTROL:
        Update item fields conditioned on version == expected_version.
        Atomically increments version and event_seq.
        If the version changed in the meantime, raises PreconditionFailedError (412).
        """
        now = utc_now()
        update_set = {
            **fields_to_set,
            "last_activity_at": now,
            "updated_at": now,
        }
        updated = await self.db.work_items.find_one_and_update(
            {"_id": item_id, "version": expected_version},
            {
                "$set": update_set,
                "$inc": {"version": 1, "event_seq": 1},
            },
            return_document=ReturnDocument.AFTER,
            session=session,
        )
        if not updated:
            current = await self.db.work_items.find_one({"_id": item_id}, session=session)
            if not current:
                raise ValueError(f"Item {item_id} not found.")
            raise PreconditionFailedError(
                detail=f"Stale version. Requested version {expected_version}, but current version is {current.get('version')}.",
                meta={"current_version": current.get("version")},
            )
        return updated

    async def list_items_keyset(
        self,
        team_ids: List[str],
        *,
        view: Optional[str] = None,
        user_id: Optional[str] = None,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        assignee_id: Optional[str] = None,
        cursor_data: Optional[Tuple[str, datetime, str]] = None,  # (priority, updated_at, _id)
        limit: int = 25,
    ) -> Tuple[List[Dict[str, Any]], bool]:
        """
        Keyset-paginated read query using compound index:
        (team_id, priority, updated_at DESC, _id ASC).
        Guarantees bounded reads and O(1) performance at depth without skip().
        """
        query: Dict[str, Any] = {"team_id": {"$in": team_ids}}

        # View filters
        now = utc_now()
        if view == "mine" and user_id:
            query["assignee_id"] = user_id
            query["status"] = {"$in": [s.value for s in ItemStatus.active_states()]}
        elif view == "created_by_me" and user_id:
            query["reporter_id"] = user_id
        elif view == "unowned_urgent":
            query["assignee_id"] = None
            query["priority"] = {"$in": [ItemPriority.P0.value, ItemPriority.P1.value]}
            query["status"] = {"$in": [s.value for s in ItemStatus.active_states()]}
        elif view == "stale":
            query["status"] = {"$in": [s.value for s in ItemStatus.active_states()]}
            query["attention_due_at"] = {"$lte": now}
        elif view == "awaiting_my_approval":
            query["status"] = ItemStatus.PENDING_APPROVAL.value

        # Explicit filters
        if status:
            query["status"] = status
        if priority:
            query["priority"] = priority
        if assignee_id is not None:
            query["assignee_id"] = assignee_id

        # Keyset pagination condition:
        # (priority > c_prio) OR (priority == c_prio AND updated_at < c_updated) OR ...
        if cursor_data:
            c_prio, c_updated, c_id = cursor_data
            query["$or"] = [
                {"priority": {"$gt": c_prio}},
                {
                    "priority": c_prio,
                    "updated_at": {"$lt": c_updated},
                },
                {
                    "priority": c_prio,
                    "updated_at": c_updated,
                    "_id": {"$gt": c_id},
                },
            ]

        page_limit = min(limit, 100)
        # Fetch limit + 1 to determine has_more
        cursor = self.db.work_items.find(
            query,
            projection=ITEM_SUMMARY_PROJECTION,
        ).sort([
            ("priority", ASCENDING),
            ("updated_at", DESCENDING),
            ("_id", ASCENDING),
        ]).limit(page_limit + 1)

        items = await cursor.to_list(length=page_limit + 1)
        has_more = len(items) > page_limit
        if has_more:
            items = items[:page_limit]

        return items, has_more
