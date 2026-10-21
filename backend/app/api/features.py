"""
Metadata and feature flag endpoints for Opsboard.
Matches docs/API_SPEC.md §3.7.
"""

from fastapi import APIRouter
from app.core.config import get_settings

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/features")
async def get_feature_flags():
    """
    Returns feature flags so the UI can adaptively hide or show AI and search features.
    """
    cfg = get_settings()
    return {
        "ai_enabled": cfg.AI_ENABLED,
        "llm_enabled": cfg.AI_ENABLED and (cfg.LLM_PROVIDER != "none"),
        "search_mode": "atlas" if cfg.ENVIRONMENT == "production" else "hybrid",
    }
