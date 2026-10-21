"""
Attention and overview dashboard service.
Computes indexed 'what requires attention' query buckets.
Matches docs/SYSTEM_DESIGN.md §5.3.
"""

from typing import Any, Dict, List
from pymongo.asynchronous.database import AsyncDatabase

from app.domain.enums import ItemPriority, ItemStatus
from app.domain.models.base import utc_now
from app.repositories.items import ITEM_SUMMARY_PROJECTION


class OverviewService:
    def __init__(self, db: AsyncDatabase) -> None:
        self.db = db

    async def get_overview(
        self,
        user_id: str,
        is_org_admin: bool,
        memberships: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Compute the 5 critical attention buckets for the user's dashboard.
        Uses indexed range queries, bounded projections, and zero memory scans.
        """
        user_team_ids = [m["team_id"] for m in memberships]
        now = utc_now()
        active_status_values = [s.value for s in ItemStatus.active_states()]

        # 1. awaiting_my_approval (lead in team)
        lead_team_ids = [m["team_id"] for m in memberships if m["role"] == "lead"]
        approval_query = {
            "team_id": {"$in": lead_team_ids if not is_org_admin else user_team_ids},
            "status": ItemStatus.PENDING_APPROVAL.value,
        }

        # 2. overdue_mine
        overdue_query = {
            "assignee_id": user_id,
            "status": {"$in": active_status_values},
            "due_at": {"$ne": None, "$lt": now},
        }

        # 3. unowned_urgent (P0 / P1 unassigned in user's teams)
        unowned_query = {
            "team_id": {"$in": user_team_ids},
            "assignee_id": None,
            "priority": {"$in": [ItemPriority.P0.value, ItemPriority.P1.value]},
            "status": {"$in": active_status_values},
        }

        # 4. stale (attention_due_at exceeded)
        stale_query = {
            "team_id": {"$in": user_team_ids},
            "status": {"$in": active_status_values},
            "attention_due_at": {"$lte": now},
        }

        # 5. blocked_mine
        blocked_query = {
            "assignee_id": user_id,
            "status": ItemStatus.BLOCKED.value,
        }

        async def _fetch_bucket(query: Dict[str, Any], sample_limit: int = 5) -> Dict[str, Any]:
            count = await self.db.work_items.count_documents(query)
            cursor = self.db.work_items.find(
                query,
                projection=ITEM_SUMMARY_PROJECTION,
            ).sort("attention_due_at", 1).limit(sample_limit)
            items = await cursor.to_list(length=sample_limit)
            return {"count": count, "items": items}

        return {
            "awaiting_my_approval": await _fetch_bucket(approval_query),
            "overdue_mine": await _fetch_bucket(overdue_query),
            "unowned_urgent": await _fetch_bucket(unowned_query),
            "stale": await _fetch_bucket(stale_query),
            "blocked_mine": await _fetch_bucket(blocked_query),
            "computed_at": now.isoformat(),
        }
