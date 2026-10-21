"""
Team domain models and schemas.
"""

from datetime import datetime
from typing import Optional, List
from pydantic import Field

from app.domain.models.base import BaseSchema, MongoDocument, generate_id
from app.domain.models.user import MembershipResponse


class Team(MongoDocument):
    """
    Team entity. Owns work items and item key counter.
    Example key prefixes: 'OPS', 'INC', 'PAY', 'ENG'.
    """
    id: str = Field(default_factory=lambda: generate_id("team"), alias="_id")
    name: str = Field(min_length=2, max_length=100)
    key_prefix: str = Field(min_length=2, max_length=10, pattern=r"^[A-Z0-9]+$")
    description: Optional[str] = Field(default=None, max_length=500)
    item_counter: int = Field(default=0, ge=0)


class TeamCreate(BaseSchema):
    """Payload to create a new team."""
    name: str = Field(min_length=2, max_length=100)
    key_prefix: str = Field(min_length=2, max_length=10, pattern=r"^[A-Z0-9]+$")
    description: Optional[str] = Field(default=None, max_length=500)


class TeamResponse(BaseSchema):
    """Team response representation."""
    id: str
    name: str
    key_prefix: str
    description: Optional[str] = None
    item_counter: int
    created_at: datetime
    updated_at: datetime


class TeamWithMemberships(TeamResponse):
    """Team response enriched with current memberships."""
    memberships: List[MembershipResponse] = Field(default_factory=list)
