"""
Server-Sent Events (SSE) real-time streaming endpoint.
Delivers hints, not data, scoped to the caller's team memberships.
Matches docs/SYSTEM_DESIGN.md §7.6 and docs/API_SPEC.md §3.9.
"""

import asyncio
from datetime import datetime, timezone
import json
import logging
from typing import AsyncGenerator
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import get_current_user_and_memberships
from app.db.client import get_database
from app.domain.models.base import utc_now
from app.repositories.events import EventRepository
from app.repositories.teams import TeamRepository

logger = logging.getLogger("opsboard.stream")
router = APIRouter(tags=["stream"])


@router.get("/stream")
async def stream_events(
    request: Request,
    auth_data: tuple = Depends(get_current_user_and_memberships),
    db: AsyncDatabase = Depends(get_database),
):
    """
    Open an SSE connection to receive live operational hints.
    Events include item.changed, notification, and heartbeat comments.
    """
    user, memberships = auth_data
    user_id = user["id"]
    is_org_admin = user.get("is_org_admin", False)

    async def event_generator() -> AsyncGenerator[str, None]:
        # 1. Send initial hello event
        hello_data = {"server_time": datetime.now(timezone.utc).isoformat()}
        yield f"event: hello\ndata: {json.dumps(hello_data)}\n\n"

        event_repo = EventRepository(db)
        team_repo = TeamRepository(db)

        # Track last seen event seq / id
        last_seen_id = None
        # Quick lookup for latest events initially
        initial_events = await event_repo.get_recent_events(limit=1)
        if initial_events:
            last_seen_id = initial_events[0]["_id"]

        heartbeat_interval = 15.0
        poll_interval = 2.0
        time_since_heartbeat = 0.0

        membership_refresh_timer = 0.0
        current_memberships = memberships

        while True:
            if await request.is_disconnected():
                break

            await asyncio.sleep(poll_interval)
            time_since_heartbeat += poll_interval
            membership_refresh_timer += poll_interval

            # Periodically re-read memberships every 60s (SYSTEM_DESIGN §7.6)
            if membership_refresh_timer >= 60.0:
                current_memberships = await team_repo.get_memberships_for_user(user_id)
                membership_refresh_timer = 0.0

            allowed_teams = {str(m["team_id"]) for m in current_memberships}

            # Poll for newer events since last_seen_id
            try:
                filter_q = {}
                if last_seen_id:
                    filter_q["_id"] = {"$gt": last_seen_id}

                new_events = await event_repo.find_since(filter_q, limit=20)
                for evt in new_events:
                    last_seen_id = evt["_id"]
                    event_team_id = str(evt.get("team_id", ""))

                    # Authorization check: only deliver hints for caller's teams
                    if is_org_admin or event_team_id in allowed_teams:
                        hint_payload = {
                            "item_id": str(evt.get("item_id", "")),
                            "key": evt.get("key", ""),
                            "team_id": event_team_id,
                            "version": evt.get("item_version", 1),
                            "event_seq": evt.get("seq", 0),
                            "type": evt.get("type", ""),
                            "actor_id": str(evt.get("actor_id", "")),
                        }
                        yield f"event: item.changed\ndata: {json.dumps(hint_payload)}\n\n"

            except Exception as e:
                logger.error("Error polling change stream for SSE client %s: %s", user_id, e)

            # Send heartbeat comment every 15s
            if time_since_heartbeat >= heartbeat_interval:
                yield ": heartbeat\n\n"
                time_since_heartbeat = 0.0

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
