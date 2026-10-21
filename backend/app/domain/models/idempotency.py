"""
Idempotency record domain models for mutation replay and safe client retries.
"""

from datetime import datetime
from typing import Optional, Any, Dict
from pydantic import Field

from app.domain.models.base import MongoDocument, generate_id


class IdempotencyRecord(MongoDocument):
    """
    Persisted idempotency key document.
    Unique compound index: (user_id, key).
    TTL index on `expires_at` cleans up keys after 24 hours.
    """
    id: str = Field(default_factory=lambda: generate_id("idem"), alias="_id")
    user_id: str
    key: str = Field(min_length=1, max_length=128)
    request_hash: str = Field(description="SHA-256 hash of HTTP method, path, and normalized body")
    response_status: Optional[int] = None
    response_body: Optional[Any] = None
    response_headers: Optional[Dict[str, str]] = None
    expires_at: datetime
