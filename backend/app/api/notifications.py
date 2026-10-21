"""
In-app notifications API endpoints.
Matches docs/API_SPEC.md §3.5.
"""

from typing import Any, Dict, List
from fastapi import APIRouter, Depends, Query
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import get_current_user_and_memberships
from app.db.client import get_database
from app.repositories.notifications import NotificationRepository

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=List[Dict[str, Any]])
async def list_notifications(
    unread_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=100),
    auth_data: tuple = Depends(get_current_user_and_memberships),
    db: AsyncDatabase = Depends(get_database),
):
    """Retrieve in-app notifications for authenticated user."""
    user, _ = auth_data
    repo = NotificationRepository(db)
    return await repo.list_for_user(user["id"], unread_only=unread_only, limit=limit)


@router.post("/{notification_id}/read", status_code=204)
async def mark_notification_read(
    notification_id: str,
    auth_data: tuple = Depends(get_current_user_and_memberships),
    db: AsyncDatabase = Depends(get_database),
):
    """Mark a notification as read."""
    user, _ = auth_data
    repo = NotificationRepository(db)
    await repo.mark_as_read(notification_id, user["id"])
    return None


@router.post("/read-all", status_code=204)
async def mark_all_read(
    auth_data: tuple = Depends(get_current_user_and_memberships),
    db: AsyncDatabase = Depends(get_database),
):
    """Mark all notifications as read for current user."""
    user, _ = auth_data
    repo = NotificationRepository(db)
    await repo.mark_all_as_read(user["id"])
    return None
