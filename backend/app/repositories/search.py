"""
Repository for full-text and autocomplete search over work_items.
Guarantees team-level authorization filter is embedded into the query.
Matches docs/DATA_MODEL.md §2.5 and docs/SYSTEM_DESIGN.md §7.3.
"""

import re
from typing import Any, Dict, List, Optional
from pymongo.asynchronous.database import AsyncDatabase


class SearchRepository:
    def __init__(self, db: AsyncDatabase):
        self.db = db
        self.items = db.work_items

    async def search_items(
        self,
        query: str,
        team_ids: List[str],
        status_filter: Optional[List[str]] = None,
        priority_filter: Optional[List[str]] = None,
        limit: int = 25,
        autocomplete: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Executes search with team_id pre-filter.
        Tries Atlas Search; falls back to bounded regex prefix match.
        """
        if not team_ids:
            return []

        # 1. Attempt Atlas Search pipeline
        try:
            must_clauses = [
                {
                    "text": {
                        "query": query,
                        "path": ["title", "description", "key", "tags"],
                    }
                }
            ]
            filter_clauses = [
                {"in": {"path": "team_id", "value": team_ids}}
            ]
            if status_filter:
                filter_clauses.append({"in": {"path": "status", "value": status_filter}})
            if priority_filter:
                filter_clauses.append({"in": {"path": "priority", "value": priority_filter}})

            pipeline = [
                {
                    "$search": {
                        "index": "work_items_search",
                        "compound": {
                            "must": must_clauses,
                            "filter": filter_clauses,
                        },
                    }
                },
                {"$limit": limit},
            ]
            if autocomplete:
                pipeline.append({"$project": {"key": 1, "title": 1, "status": 1}})
            else:
                pipeline.append({
                    "$project": {
                        "title": 1, "key": 1, "type": 1, "priority": 1,
                        "status": 1, "team_id": 1, "assignee_id": 1,
                        "reporter_id": 1, "due_at": 1, "created_at": 1,
                        "updated_at": 1, "last_activity_at": 1, "version": 1,
                        "score": {"$meta": "searchScore"},
                    }
                })

            cursor = await self.items.aggregate(pipeline)
            results = await cursor.to_list(length=limit)
            if results:
                return results
        except Exception:
            # Fallback for local testing or when Atlas Search is building
            pass

        # 2. Bounded fallback: regex search within caller's teams
        escaped_q = re.escape(query.strip())
        mongo_filter: Dict[str, Any] = {
            "team_id": {"$in": team_ids},
            "$or": [
                {"key": {"$regex": f"^{escaped_q}", "$options": "i"}},
                {"title": {"$regex": escaped_q, "$options": "i"}},
                {"tags": {"$in": [query.strip().lower()]}},
            ],
        }
        if status_filter:
            mongo_filter["status"] = {"$in": status_filter}
        if priority_filter:
            mongo_filter["priority"] = {"$in": priority_filter}

        projection = (
            {"key": 1, "title": 1, "status": 1}
            if autocomplete
            else {
                "title": 1, "key": 1, "type": 1, "priority": 1,
                "status": 1, "team_id": 1, "assignee_id": 1,
                "reporter_id": 1, "due_at": 1, "created_at": 1,
                "updated_at": 1, "last_activity_at": 1, "version": 1,
            }
        )

        cursor = self.items.find(mongo_filter, projection).sort("last_activity_at", -1).limit(limit)
        return await cursor.to_list(length=limit)
