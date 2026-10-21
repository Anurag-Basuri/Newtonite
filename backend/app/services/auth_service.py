"""
Authentication and session management service.
Handles credentials verification, session generation, and user context loading.
"""

from typing import Any, Dict, Optional, Tuple
from pymongo.asynchronous.database import AsyncDatabase

from app.core.errors import UnauthenticatedError
from app.repositories.users import UserRepository
from app.repositories.teams import TeamRepository


class AuthService:
    def __init__(self, db: AsyncDatabase) -> None:
        self.db = db
        self.users = UserRepository(db)
        self.teams = TeamRepository(db)

    async def login(
        self,
        email: str,
        password: str,
        user_agent: str = "",
        ip: str = "",
    ) -> Tuple[Dict[str, Any], str, list[Dict[str, Any]]]:
        """
        Authenticate user and return (user_doc, raw_session_token, memberships).
        """
        user = await self.users.get_by_email(email)
        if not user or not user.get("is_active", True):
            raise UnauthenticatedError(detail="Invalid email or password.")

        if not self.users.verify_password(user["password_hash"], password):
            raise UnauthenticatedError(detail="Invalid email or password.")

        # Create session
        token = await self.users.create_session(user["_id"], user_agent=user_agent, ip=ip)
        memberships = await self.teams.get_memberships_for_user(user["_id"])

        user_summary = {
            "id": user["_id"],
            "name": user["name"],
            "email": user["email"],
            "is_org_admin": user.get("is_org_admin", False),
        }
        return user_summary, token, memberships

    async def logout(self, token: str) -> None:
        await self.users.delete_session(token)

    async def get_current_user_and_memberships(
        self,
        token: Optional[str],
    ) -> Tuple[Dict[str, Any], list[Dict[str, Any]]]:
        """
        Validate session token and return user profile + memberships.
        Raises UnauthenticatedError if session is missing or invalid.
        """
        if not token:
            raise UnauthenticatedError(detail="Authentication session required.")

        user = await self.users.get_session_user(token)
        if not user or not user.get("is_active", True):
            raise UnauthenticatedError(detail="Session expired or invalid.")

        memberships = await self.teams.get_memberships_for_user(user["_id"])
        user_summary = {
            "id": user["_id"],
            "name": user["name"],
            "email": user["email"],
            "is_org_admin": user.get("is_org_admin", False),
        }
        return user_summary, memberships
