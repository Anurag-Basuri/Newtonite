"""
Teams and memberships API endpoints.
Matches docs/API_SPEC.md §3.2.
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import get_current_user_and_memberships
from app.core.errors import ForbiddenError, NotFoundError
from app.db.client import get_database
from app.domain.enums import TeamRole
from app.repositories.teams import TeamRepository

router = APIRouter(prefix="/teams", tags=["teams"])


class CreateTeamRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    slug: str = Field(min_length=1, max_length=50)
    key_prefix: str = Field(min_length=2, max_length=10)


class AddMemberRequest(BaseModel):
    user_id: str
    role: TeamRole = TeamRole.MEMBER


class UpdateMemberRoleRequest(BaseModel):
    role: TeamRole


@router.get("", response_model=List[Dict[str, Any]])
async def list_my_teams(
    auth_data: tuple = Depends(get_current_user_and_memberships),
):
    """List teams caller belongs to, with their roles."""
    user, memberships = auth_data
    return memberships


@router.get("/{team_id}/members", response_model=List[Dict[str, Any]])
async def list_team_members(
    team_id: str,
    auth_data: tuple = Depends(get_current_user_and_memberships),
    db: AsyncDatabase = Depends(get_database),
):
    """List all members of a team. Requires membership in the team or org admin."""
    user, memberships = auth_data
    is_org_admin = user.get("is_org_admin", False)
    is_member = any(m["team_id"] == team_id for m in memberships)

    if not is_member and not is_org_admin:
        raise NotFoundError(detail="Team not found.")

    repo = TeamRepository(db)
    return await repo.get_team_members(team_id)


@router.post("", status_code=201)
async def create_team(
    payload: CreateTeamRequest,
    auth_data: tuple = Depends(get_current_user_and_memberships),
    db: AsyncDatabase = Depends(get_database),
):
    """Create team. Requires org admin."""
    user, _ = auth_data
    if not user.get("is_org_admin", False):
        raise ForbiddenError(detail="Only org admins can create teams.")

    repo = TeamRepository(db)
    return await repo.create_team(payload.name, payload.slug, payload.key_prefix)


@router.post("/{team_id}/members", status_code=201)
async def add_team_member(
    team_id: str,
    payload: AddMemberRequest,
    auth_data: tuple = Depends(get_current_user_and_memberships),
    db: AsyncDatabase = Depends(get_database),
):
    """Add member to team. Requires org admin."""
    user, _ = auth_data
    if not user.get("is_org_admin", False):
        raise ForbiddenError(detail="Only org admins can manage team memberships.")

    repo = TeamRepository(db)
    return await repo.add_membership(team_id, payload.user_id, payload.role, added_by=user["id"])


@router.patch("/{team_id}/members/{user_id}")
async def update_team_member(
    team_id: str,
    user_id: str,
    payload: UpdateMemberRoleRequest,
    auth_data: tuple = Depends(get_current_user_and_memberships),
    db: AsyncDatabase = Depends(get_database),
):
    """Update team member role. Requires org admin."""
    user, _ = auth_data
    if not user.get("is_org_admin", False):
        raise ForbiddenError(detail="Only org admins can update member roles.")

    repo = TeamRepository(db)
    await repo.update_membership_role(team_id, user_id, payload.role)
    return {"status": "ok"}


@router.delete("/{team_id}/members/{user_id}", status_code=204)
async def remove_team_member(
    team_id: str,
    user_id: str,
    auth_data: tuple = Depends(get_current_user_and_memberships),
    db: AsyncDatabase = Depends(get_database),
):
    """Remove member from team. Requires org admin."""
    user, _ = auth_data
    if not user.get("is_org_admin", False):
        raise ForbiddenError(detail="Only org admins can remove members.")

    repo = TeamRepository(db)
    await repo.remove_membership(team_id, user_id)
    return None
