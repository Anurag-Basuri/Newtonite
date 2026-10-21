"""
Search service handling full-text search and command palette autocomplete.
Matches docs/SYSTEM_DESIGN.md §7.3 and docs/API_SPEC.md §3.6.
"""

from typing import Any, Dict, List, Optional
from pymongo.asynchronous.database import AsyncDatabase

from app.core.errors import DomainError
from app.repositories.search import SearchRepository


class SearchService:
    def __init__(self, db: AsyncDatabase):
        self.db = db
        self.repo = SearchRepository(db)

    async def search(
        self,
        user: Dict[str, Any],
        memberships: List[Dict[str, Any]],
        q: str,
        team_id: Optional[List[str]] = None,
        status: Optional[List[str]] = None,
        priority: Optional[List[str]] = None,
        limit: int = 25,
        mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        if len(q.strip()) < 2:
            raise DomainError(
                status_code=422,
                code="INVALID_QUERY",
                message="Search query must contain at least 2 characters.",
            )

        user_team_ids = [str(m["team_id"]) for m in memberships]
        if not user_team_ids and not user.get("is_org_admin"):
            return {"items": [], "next_cursor": None, "has_more": False}

        # Validate team filter
        if team_id:
            for tid in team_id:
                if tid not in user_team_ids and not user.get("is_org_admin"):
                    raise DomainError(
                        status_code=404,
                        code="RESOURCE_NOT_FOUND",
                        message=f"Team {tid} not found or inaccessible.",
                    )
            target_teams = team_id
        else:
            target_teams = user_team_ids

        autocomplete = mode == "autocomplete"
        results = await self.repo.search_items(
            query=q,
            team_ids=target_teams,
            status_filter=status,
            priority_filter=priority,
            limit=limit,
            autocomplete=autocomplete,
        )

        # Stringify ObjectIds
        formatted = []
        for r in results:
            doc = dict(r)
            if "_id" in doc:
                doc["id"] = str(doc.pop("_id"))
            if "team_id" in doc:
                doc["team_id"] = str(doc["team_id"])
            if "reporter_id" in doc:
                doc["reporter_id"] = str(doc["reporter_id"])
            if "assignee_id" in doc and doc["assignee_id"]:
                doc["assignee_id"] = str(doc["assignee_id"])
            formatted.append(doc)

        return {
            "items": formatted,
            "next_cursor": None,
            "has_more": False,
        }
