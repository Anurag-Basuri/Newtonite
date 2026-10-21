"""
Team and membership data access repository.
Manages team metadata, multi-team memberships, and atomic per-team item counters.
"""

from typing import Any, Dict, List, Optional
from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.asynchronous.client_session import AsyncClientSession

from app.domain.enums import TeamRole
from app.domain.models.base import generate_id, utc_now


class TeamRepository:
    def __init__(self, db: AsyncDatabase) -> None:
        self.db = db

    async def get_by_id(self, team_id: str) -> Optional[Dict[str, Any]]:
        return await self.db.teams.find_one({"_id": team_id})

    async def get_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:
        return await self.db.teams.find_one({"slug": slug.strip().lower()})

    async def list_all_teams(self) -> List[Dict[str, Any]]:
        """List all registered teams in the organisation."""
        cursor = self.db.teams.find({})
        return await cursor.to_list(length=100)

    async def create_team(self, name: str, slug: str, key_prefix: str) -> Dict[str, Any]:
        team_id = generate_id("team")
        doc = {
            "_id": team_id,
            "name": name.strip(),
            "slug": slug.strip().lower(),
            "key_prefix": key_prefix.strip().upper(),
            "item_counter": 0,
            "created_at": utc_now(),
            "updated_at": utc_now(),
        }
        await self.db.teams.insert_one(doc)
        return doc

    async def increment_item_counter(
        self,
        session: AsyncClientSession,
        team_id: str,
    ) -> tuple[str, int]:
        """
        Atomically increment the team's item counter inside the item creation transaction.
        Returns (key_prefix, next_counter_value).
        """
        team = await self.db.teams.find_one_and_update(
            {"_id": team_id},
            {"$inc": {"item_counter": 1}},
            return_document=ReturnDocument.AFTER,
            session=session,
        )
        if not team:
            raise ValueError(f"Team {team_id} does not exist.")
        return team["key_prefix"], team["item_counter"]

    async def get_memberships_for_user(self, user_id: str) -> List[Dict[str, Any]]:
        """Return all team memberships for a given user, populated with team metadata."""
        cursor = self.db.memberships.find({"user_id": user_id})
        memberships = await cursor.to_list(length=100)
        if not memberships:
            return []

        team_ids = [m["team_id"] for m in memberships]
        teams_cursor = self.db.teams.find({"_id": {"$in": team_ids}})
        teams_map = {t["_id"]: t for t in await teams_cursor.to_list(length=100)}

        results = []
        for m in memberships:
            t = teams_map.get(m["team_id"])
            if t:
                results.append({
                    "id": m["_id"],
                    "team_id": m["team_id"],
                    "user_id": m["user_id"],
                    "role": m["role"],
                    "team": {
                        "id": t["_id"],
                        "name": t["name"],
                        "slug": t["slug"],
                        "key_prefix": t["key_prefix"],
                    },
                })
        return results

    async def get_membership(self, team_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        return await self.db.memberships.find_one({"team_id": team_id, "user_id": user_id})

    async def get_team_members(self, team_id: str) -> List[Dict[str, Any]]:
        """List all members of a team populated with basic user profile info."""
        cursor = self.db.memberships.find({"team_id": team_id})
        memberships = await cursor.to_list(length=100)
        if not memberships:
            return []

        user_ids = [m["user_id"] for m in memberships]
        users_cursor = self.db.users.find(
            {"_id": {"$in": user_ids}},
            projection={"name": 1, "email": 1, "is_active": 1},
        )
        users_map = {u["_id"]: u for u in await users_cursor.to_list(length=100)}

        results = []
        for m in memberships:
            u = users_map.get(m["user_id"])
            if u:
                results.append({
                    "id": m["_id"],
                    "user_id": m["user_id"],
                    "team_id": team_id,
                    "role": m["role"],
                    "user": {
                        "id": u["_id"],
                        "name": u["name"],
                        "email": u["email"],
                    },
                })
        return results

    async def add_membership(
        self,
        team_id: str,
        user_id: str,
        role: TeamRole,
        added_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        membership_id = generate_id("mem")
        role_val = role.value if hasattr(role, "value") else str(role)
        doc = {
            "_id": membership_id,
            "team_id": team_id,
            "user_id": user_id,
            "role": role_val,
            "added_by": added_by,
            "created_at": utc_now(),
        }
        await self.db.memberships.insert_one(doc)
        return doc

    async def update_membership_role(self, team_id: str, user_id: str, role: TeamRole) -> None:
        role_val = role.value if hasattr(role, "value") else str(role)
        await self.db.memberships.update_one(
            {"team_id": team_id, "user_id": user_id},
            {"$set": {"role": role_val}},
        )

    async def remove_membership(self, team_id: str, user_id: str) -> None:
        await self.db.memberships.delete_one({"team_id": team_id, "user_id": user_id})
