"""
Approvals data access repository.
Enforces that an item has at most one pending approval at any time,
and uses conditional updates to ensure an approval can only be decided once.
Matches docs/DATA_MODEL.md §2.7.
"""

from typing import Any, Dict, Optional
from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.asynchronous.client_session import AsyncClientSession

from app.domain.enums import ApprovalStatus
from app.domain.models.base import generate_id, utc_now


class ApprovalRepository:
    def __init__(self, db: AsyncDatabase) -> None:
        self.db = db

    async def get_by_id(self, approval_id: str) -> Optional[Dict[str, Any]]:
        return await self.db.approvals.find_one({"_id": approval_id})

    async def get_pending_for_item(self, item_id: str) -> Optional[Dict[str, Any]]:
        return await self.db.approvals.find_one({
            "item_id": item_id,
            "status": ApprovalStatus.PENDING.value,
        })

    async def create_approval_in_session(
        self,
        session: AsyncClientSession,
        item_id: str,
        team_id: str,
        requested_by: str,
        request_note: str,
    ) -> Dict[str, Any]:
        """
        Create a new approval request inside the transaction.
        Database partial unique index uq_approvals_single_pending guarantees that
        no two concurrent pending approvals can exist for the same item.
        """
        approval_id = generate_id("apr")
        now = utc_now()
        doc = {
            "_id": approval_id,
            "item_id": item_id,
            "team_id": team_id,
            "status": ApprovalStatus.PENDING.value,
            "requested_by": requested_by,
            "requested_at": now,
            "request_note": request_note,
            "decided_by": None,
            "decided_at": None,
            "decision_reason": None,
            "created_at": now,
            "updated_at": now,
        }
        await self.db.approvals.insert_one(doc, session=session)
        return doc

    async def decide_approval_cas(
        self,
        session: AsyncClientSession,
        approval_id: str,
        status: ApprovalStatus,
        decided_by: str,
        decision_reason: str,
    ) -> Dict[str, Any]:
        """
        ATOMIC CONDITIONAL UPDATE:
        Decide an approval request. Precondition `status: pending` is in the filter,
        preventing double-deciding if two leads review at the same time.
        """
        now = utc_now()
        status_val = status.value if hasattr(status, "value") else str(status)
        updated = await self.db.approvals.find_one_and_update(
            {"_id": approval_id, "status": ApprovalStatus.PENDING.value},
            {
                "$set": {
                    "status": status_val,
                    "decided_by": decided_by,
                    "decided_at": now,
                    "decision_reason": decision_reason,
                    "updated_at": now,
                }
            },
            return_document=ReturnDocument.AFTER,
            session=session,
        )
        if not updated:
            current = await self.db.approvals.find_one({"_id": approval_id}, session=session)
            if not current:
                raise ValueError(f"Approval {approval_id} not found.")
            raise ValueError(f"Approval has already been decided: status={current.get('status')}")
        return updated
