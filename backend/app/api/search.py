"""
Search API endpoints.
Matches docs/API_SPEC.md §3.6.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import get_current_user_and_memberships
from app.db.client import get_database
from app.services.search_service import SearchService

router = APIRouter(tags=["search"])


@router.get("/search")
async def search_items(
    q: str = Query(..., min_length=1, description="Search query string"),
    team_id: Optional[List[str]] = Query(None),
    status: Optional[List[str]] = Query(None),
    priority: Optional[List[str]] = Query(None),
    limit: int = Query(25, ge=1, le=100),
    cursor: Optional[str] = Query(None),
    mode: Optional[str] = Query(None, description="'autocomplete' for command palette"),
    auth_data: tuple = Depends(get_current_user_and_memberships),
    db: AsyncDatabase = Depends(get_database),
):
    """
    Search work items across authorized teams.
    Supports full-text search and lightweight autocomplete.
    """
    user, memberships = auth_data
    service = SearchService(db)
    return await service.search(
        user=user,
        memberships=memberships,
        q=q,
        team_id=team_id,
        status=status,
        priority=priority,
        limit=limit,
        mode=mode,
    )
