"""
Users API endpoints.
Matches docs/API_SPEC.md §3.2.
"""

from typing import Any, Dict, List
from fastapi import APIRouter, Depends, Query
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import get_current_user_and_memberships
from app.core.errors import ForbiddenError
from app.db.client import get_database
from app.repositories.users import UserRepository

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=List[Dict[str, Any]])
async def search_users(
    q: str = Query("", description="Search term for name or email"),
    auth_data: tuple = Depends(get_current_user_and_memberships),
    db: AsyncDatabase = Depends(get_database),
):
    """Search users (to add members). Requires org admin."""
    user, _ = auth_data
    if not user.get("is_org_admin", False):
        raise ForbiddenError(detail="Only org admins can search users.")

    repo = UserRepository(db)
    return await repo.search_users(query=q)
