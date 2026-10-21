"""
Overview and Attention dashboard domain models.
"""

from typing import Dict, List
from pydantic import Field

from app.domain.enums import AttentionReason
from app.domain.models.base import BaseSchema
from app.domain.models.work_item import WorkItemSummary


class AttentionBucketSummary(BaseSchema):
    """Counts and preview items for a specific attention category."""
    bucket: AttentionReason
    count: int = Field(ge=0)
    has_more: bool = False
    items: List[WorkItemSummary] = Field(default_factory=list)


class OverviewResponse(BaseSchema):
    """
    Overview response for the triage/command dashboard.
    Aggregates high-priority work requiring immediate action.
    """
    buckets: Dict[str, AttentionBucketSummary] = Field(default_factory=dict)
    total_attention_count: int = 0
