"""
AI and semantic search API endpoints.
Matches docs/API_SPEC.md §3.7.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import get_current_user_and_memberships
from app.db.client import get_database
from app.domain.models.ai import AskQuestionRequest
from app.services.ai_service import AIService

router = APIRouter(tags=["ai"])


class SimilarQueryRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(default="", max_length=20000)
    team_id: Optional[str] = None


@router.post("/ai/similar")
async def find_similar_items(
    payload: SimilarQueryRequest,
    limit: int = Query(5, ge=1, le=20),
    auth_data: tuple = Depends(get_current_user_and_memberships),
    db: AsyncDatabase = Depends(get_database),
):
    """
    Surfaces semantically similar items for the create-item form.
    Answers 'are two people working on the same issue without realising?'
    """
    user, memberships = auth_data
    service = AIService(db)
    res = await service.find_similar_items(
        user=user,
        memberships=memberships,
        title=payload.title,
        description=payload.description or "",
        team_id=payload.team_id,
        limit=limit,
    )
    # Return format per API_SPEC §3.7: {items: [{key, title, status, assignee, score}]}
    formatted_items = [
        {
            "key": m.item_key,
            "title": m.title,
            "status": m.status.value,
            "priority": m.priority.value,
            "assignee": m.assignee_id,
            "score": m.score,
        }
        for m in res.matches
    ]
    return {"items": formatted_items}


@router.get("/items/{identifier}/similar")
async def get_similar_items_for_item(
    identifier: str,
    limit: int = Query(5, ge=1, le=20),
    auth_data: tuple = Depends(get_current_user_and_memberships),
    db: AsyncDatabase = Depends(get_database),
):
    """
    Retrieve related items for an existing work item, excluding itself.
    Scoped strictly to caller's teams.
    """
    user, memberships = auth_data
    service = AIService(db)
    res = await service.find_similar_for_item(
        user=user,
        memberships=memberships,
        identifier=identifier,
        limit=limit,
    )
    formatted_items = [
        {
            "key": m.item_key,
            "title": m.title,
            "status": m.status.value,
            "priority": m.priority.value,
            "assignee": m.assignee_id,
            "score": m.score,
        }
        for m in res.matches
    ]
    return {"items": formatted_items}


@router.post("/ai/ask")
async def ask_question(
    payload: AskQuestionRequest,
    auth_data: tuple = Depends(get_current_user_and_memberships),
    db: AsyncDatabase = Depends(get_database),
):
    """
    Natural-language question answering grounded in team operational history.
    Returns grounded answer with validated [S#] citations.
    """
    user, memberships = auth_data
    service = AIService(db)
    res = await service.ask(
        user=user,
        memberships=memberships,
        question=payload.question,
        team_id=payload.team_id,
        item_id=payload.item_id,
    )

    # Format per API_SPEC §3.7
    citations_data = [
        {
            "marker": c.marker,
            "item_key": c.item_key,
            "item_id": c.item_id,
            "kind": c.kind.value,
            "snippet": c.snippet,
            "url": f"/items/{c.item_key}",
        }
        for c in res.citations
    ]

    retrieved_data = [
        {
            "marker": r.marker,
            "item_key": r.item_key,
            "kind": r.kind.value,
            "score": r.score,
            "text": r.snippet,
        }
        for r in res.retrieved_passages
    ]

    return {
        "question": res.question,
        "answer": res.answer,
        "degraded": res.degraded,
        "citations": citations_data,
        "retrieved": retrieved_data,
        "timings_ms": {"latency": res.latency_ms},
    }
