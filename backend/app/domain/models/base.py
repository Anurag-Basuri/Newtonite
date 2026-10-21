"""
Base schemas, ID generators, and timestamp helpers.
"""

from datetime import datetime, timezone
import uuid
from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(timezone.utc)


def generate_id(prefix: str = "") -> str:
    """Generate a clean, collision-free unique identifier with optional domain prefix."""
    unique = uuid.uuid4().hex
    return f"{prefix}_{unique}" if prefix else unique


class BaseSchema(BaseModel):
    """Base Pydantic schema with standard serialization and validation settings."""
    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
        validate_assignment=True,
        arbitrary_types_allowed=True,
        json_encoders={
            datetime: lambda dt: dt.isoformat(),
        },
    )


class MongoDocument(BaseSchema):
    """
    Base model for MongoDB documents.
    Maps '_id' in MongoDB to 'id' attribute in Python.
    """
    id: str = Field(default_factory=generate_id, alias="_id")
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    def to_mongo_dict(self) -> dict:
        """Dump model suitable for direct MongoDB insertion/replacement with '_id'."""
        return self.model_dump(by_alias=True)
