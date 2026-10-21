"""
User and session data access repository.
Uses argon2id for password hashing and opaque session tokens in MongoDB.
"""

from datetime import timedelta
import hashlib
import secrets
from typing import Any, Dict, Optional
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import get_settings
from app.domain.models.base import generate_id, utc_now

ph = PasswordHasher()


class UserRepository:
    def __init__(self, db: AsyncDatabase) -> None:
        self.db = db

    @staticmethod
    def hash_password(password: str) -> str:
        return ph.hash(password)

    @staticmethod
    def verify_password(password_hash: str, password: str) -> bool:
        try:
            return ph.verify(password_hash, password)
        except VerifyMismatchError:
            return False

    async def get_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        return await self.db.users.find_one({"_id": user_id})

    async def get_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        return await self.db.users.find_one({"email": email.strip().lower()})

    async def search_users(self, query: str = "", limit: int = 50) -> list[Dict[str, Any]]:
        """Search users by name or email."""
        import re
        filter_dict: Dict[str, Any] = {}
        if query and query.strip():
            escaped = re.escape(query.strip())
            filter_dict = {
                "$or": [
                    {"name": {"$regex": escaped, "$options": "i"}},
                    {"email": {"$regex": escaped, "$options": "i"}},
                ]
            }
        cursor = self.db.users.find(
            filter_dict,
            projection={"_id": 1, "name": 1, "email": 1, "is_active": 1, "is_org_admin": 1},
        ).sort("name", 1)
        users = await cursor.to_list(length=limit)
        return [
            {
                "id": u["_id"],
                "name": u.get("name"),
                "email": u.get("email"),
                "is_active": u.get("is_active", True),
                "is_org_admin": u.get("is_org_admin", False),
            }
            for u in users
        ]

    async def create_user(
        self,
        name: str,
        email: str,
        password: str,
        *,
        is_org_admin: bool = False,
    ) -> Dict[str, Any]:
        user_id = generate_id("usr")
        doc = {
            "_id": user_id,
            "name": name.strip(),
            "email": email.strip().lower(),
            "password_hash": self.hash_password(password),
            "is_org_admin": is_org_admin,
            "is_active": True,
            "created_at": utc_now(),
            "updated_at": utc_now(),
        }
        await self.db.users.insert_one(doc)
        return doc

    # Session Management
    async def create_session(self, user_id: str, user_agent: str = "", ip: str = "") -> str:
        """
        Creates an opaque server-side session token.
        Stores SHA-256 hash of token as _id in sessions collection.
        Returns the raw opaque token to be sent in HttpOnly cookie.
        """
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        cfg = get_settings()
        expires_at = utc_now() + timedelta(hours=cfg.SESSION_TTL_HOURS)

        session_doc = {
            "_id": token_hash,
            "user_id": user_id,
            "user_agent": user_agent,
            "ip": ip,
            "created_at": utc_now(),
            "last_seen_at": utc_now(),
            "expires_at": expires_at,
        }
        await self.db.sessions.insert_one(session_doc)
        return raw_token

    async def get_session_user(self, raw_token: str) -> Optional[Dict[str, Any]]:
        """Validate raw session token and return user if active and unexpired."""
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        now = utc_now()
        session_doc = await self.db.sessions.find_one({
            "_id": token_hash,
            "expires_at": {"$gt": now},
        })
        if not session_doc:
            return None

        # Update last_seen_at
        await self.db.sessions.update_one(
            {"_id": token_hash},
            {"$set": {"last_seen_at": now}},
        )
        return await self.get_by_id(session_doc["user_id"])

    async def delete_session(self, raw_token: str) -> None:
        """Revoke a session token."""
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        await self.db.sessions.delete_one({"_id": token_hash})
