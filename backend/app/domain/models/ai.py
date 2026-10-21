"""
AI and RAG domain models, vector chunks, and Q&A citation contracts.
"""

from datetime import datetime
from typing import Optional, List
from pydantic import Field

from app.domain.enums import ChunkKind, ItemStatus, ItemPriority
from app.domain.models.base import BaseSchema, MongoDocument, utc_now


class ItemChunk(MongoDocument):
    """
    Embedded vector chunk stored in 'item_chunks' collection.
    Searchable via MongoDB Atlas Vector Search or in-memory fallback.
    Deterministic _id pattern: '{source_id}:{part}'.
    """
    id: str = Field(alias="_id", description="Deterministic ID e.g. itm_123:0 or evt_456:0")
    team_id: str = Field(description="Used for hard pre-filtering in vector queries")
    item_id: str
    item_key: str
    kind: ChunkKind
    source_id: str
    event_seq: Optional[int] = None
    author_id: Optional[str] = None
    text: str
    embedding: List[float] = Field(default_factory=list, description="Vector embedding floats")
    model: str = "BAAI/bge-small-en-v1.5"
    content_version: int = 1
    text_hash: str
    item_status: Optional[ItemStatus] = None


class SimilarItemMatch(BaseSchema):
    """Potential duplicate or related item surfaced to user."""
    item_id: str
    item_key: str
    title: str
    status: ItemStatus
    priority: ItemPriority
    assignee_id: Optional[str] = None
    score: float


class SimilarItemsResponse(BaseSchema):
    """Response containing duplicate/similar hints."""
    matches: List[SimilarItemMatch] = Field(default_factory=list)


class AskQuestionRequest(BaseSchema):
    """Query payload for natural language Q&A over team operational history."""
    question: str = Field(min_length=3, max_length=500)
    team_id: Optional[str] = None
    item_id: Optional[str] = None  # Scoped Q&A for a single item


class Citation(BaseSchema):
    """Grounded reference supporting an LLM answer."""
    marker: str = Field(description="e.g. [S1]")
    item_id: str
    item_key: str
    kind: ChunkKind
    snippet: str
    score: float


class AskQuestionResponse(BaseSchema):
    """Response with grounded answer and validated citations."""
    question: str
    answer: Optional[str] = None
    degraded: bool = False
    citations: List[Citation] = Field(default_factory=list)
    retrieved_passages: List[Citation] = Field(default_factory=list)
    latency_ms: float
