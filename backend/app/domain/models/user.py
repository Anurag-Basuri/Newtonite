"""
User, Membership, Session, and UserContext domain models.
"""

from datetime import datetime
from typing import Optional, Dict, Annotated
from pydantic import Field, StringConstraints

from app.domain.enums import TeamRole
from app.domain.models.base import BaseSchema, MongoDocument, generate_id, utc_now

EmailType = Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")]


class User(MongoDocument):
    """Registered employee / user entity."""
    id: str = Field(default_factory=lambda: generate_id("usr"), alias="_id")
    email: EmailType
    name: str = Field(min_length=1, max_length=120)
    password_hash: str
    is_org_admin: bool = False


class UserCreate(BaseSchema):
    """Payload for user registration / provisioning."""
    email: EmailType
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=128)
    is_org_admin: bool = False


class UserResponse(BaseSchema):
    """Public user response DTO."""
    id: str
    email: EmailType
    name: str
    is_org_admin: bool
    created_at: datetime


class LoginRequest(BaseSchema):
    """Credentials for authentication."""
    email: EmailType
    password: str


class Membership(MongoDocument):
    """
    User membership within a specific team.
    Unique compound constraint: (user_id, team_id).
    """
    id: str = Field(default_factory=lambda: generate_id("mem"), alias="_id")
    user_id: str
    team_id: str
    role: TeamRole = TeamRole.MEMBER


class MembershipCreate(BaseSchema):
    user_id: str
    team_id: str
    role: TeamRole = TeamRole.MEMBER


class MembershipResponse(BaseSchema):
    id: str
    user_id: str
    team_id: str
    role: TeamRole
    created_at: datetime


class Session(MongoDocument):
    """
    Server-side session document with SHA-256 token hash.
    TTL index operates on `expires_at`.
    """
    id: str = Field(default_factory=lambda: generate_id("ses"), alias="_id")
    user_id: str
    token_hash: str
    expires_at: datetime
    last_seen_at: datetime = Field(default_factory=utc_now)


class UserContext(BaseSchema):
    """
    Decoded authorization context for an authenticated request.
    Passed to domain policies to verify team-scoped permissions without extra DB queries.
    """
    user_id: str
    email: str
    name: str
    is_org_admin: bool = False
    team_roles: Dict[str, TeamRole] = Field(default_factory=dict)

    def get_role(self, team_id: str) -> Optional[TeamRole]:
        """Get role in the specified team, or None if not a member."""
        return self.team_roles.get(team_id)

    def is_member_of(self, team_id: str) -> bool:
        """True if user has any role in team or is org admin."""
        return team_id in self.team_roles or self.is_org_admin
