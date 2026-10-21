"""
Idempotency infrastructure for safe mutation retries.
Persists completed mutating responses scoped by (user_id, key).

CRITICAL INVARIANTS:
1. Idempotency records are written INSIDE the business transaction session,
   so there is zero window where the business mutation commits but the key is not recorded.
2. If a request is replayed with the exact same key and matching payload, the stored
   response is returned with header `Idempotent-Replay: true`.
3. If a request attempts to reuse an existing key with a mismatched payload,
   it is rejected with 409 IDEMPOTENCY_CONFLICT.
"""

from datetime import timedelta
import hashlib
import json
from typing import Any, Dict, Optional, Tuple
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import DuplicateKeyError

from app.core.errors import ConflictError, IdempotencyConflictError
from app.domain.models.base import utc_now


def compute_request_hash(method: str, path: str, body_bytes: bytes) -> str:
    """Compute deterministic SHA-256 hash for incoming request identification."""

    hasher = hashlib.sha256()
    hasher.update(method.upper().encode("utf-8"))
    hasher.update(path.encode("utf-8"))
    hasher.update(body_bytes)
    return hasher.hexdigest()


class IdempotencyService:
    """Coordinates idempotency checks and atomic session recordings."""

    @staticmethod
    async def get_stored_response(
        db: AsyncDatabase,
        user_id: str,
        key: str,
        request_hash: str,
    ) -> Optional[Tuple[int, Any, Dict[str, str]]]:
        """
        Check if a completed response has already been stored for this (user_id, key).
        Returns (status_code, body, headers) if found and hash matches.
        Raises ConflictError if key is reused with a different request payload.
        """
        doc = await db.idempotency.find_one({"user_id": user_id, "key": key})
        if not doc:
            return None

        # Verify payload integrity
        stored_hash = doc.get("request_hash")
        if stored_hash != request_hash:
            raise ConflictError(
                detail="Idempotency-Key was previously used with a different request payload.",
                code="IDEMPOTENCY_MISMATCH",
            )

        status_code = doc.get("response_status", 200)
        body = doc.get("response_body")
        headers = doc.get("response_headers") or {}
        headers["Idempotent-Replay"] = "true"
        return status_code, body, headers

    @staticmethod
    async def record_in_session(
        session: AsyncClientSession,
        db: AsyncDatabase,
        user_id: str,
        key: str,
        request_hash: str,
        response_status: int,
        response_body: Any,
        response_headers: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Record the completed response inside the active MongoDB transaction session.
        Guarantees that state mutation and idempotency key are atomic.
        """
        record = {
            "user_id": user_id,
            "key": key,
            "request_hash": request_hash,
            "response_status": response_status,
            "response_body": response_body,
            "response_headers": response_headers or {},
            "created_at": utc_now(),
            "expires_at": utc_now() + timedelta(hours=24),
        }
        try:
            await db.idempotency.insert_one(record, session=session)
        except DuplicateKeyError as e:
            raise IdempotencyConflictError(
                detail="Concurrent operation with this Idempotency-Key is already being processed.",
            ) from e
