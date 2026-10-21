"""
Overview API endpoint for the 'what needs attention' dashboard.
Matches docs/API_SPEC.md §3.4.
"""

from typing import Any, Dict
from fastapi import APIRouter, Depends
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import get_current_user_and_memberships
from app.db.client import get_database
from app.services.overview_service import OverviewService

router = APIRouter(prefix="/overview", tags=["overview"])


@router.get("", response_model=Dict[str, Any])
async def get_overview(
    auth_data: tuple = Depends(get_current_user_and_memberships),
    db: AsyncDatabase = Depends(get_database),
):
    """
    Compute 'what requires attention' query buckets:
    - awaiting_my_approval
    - overdue_mine
    - unowned_urgent
    - stale
    - blocked_mine
    """
    user, memberships = auth_data
    service = OverviewService(db)
    return await service.get_overview(
        user_id=user["id"],
        is_org_admin=user.get("is_org_admin", False),
        memberships=memberships,
    )
