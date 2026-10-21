"""
Repository for item_chunks (RAG vector chunks) and ai_queries.
Enforces deterministic chunk IDs, authorization pre-filtering, and vector search fallback.
Matches docs/DATA_MODEL.md §2.11 and §2.12.
"""

from datetime import datetime
import math
from typing import Any, Dict, List, Optional
from pymongo import ASCENDING, DESCENDING
from pymongo.asynchronous.database import AsyncDatabase

from app.domain.models.ai import ItemChunk


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Compute cosine similarity between two float vectors."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


class ChunkRepository:
    """Handles storage and retrieval of vector chunks and AI audit queries."""

    def __init__(self, db: AsyncDatabase):
        self.db = db
        self.chunks = db.item_chunks
        self.ai_queries = db.ai_queries

    async def upsert_chunk(self, chunk: ItemChunk) -> None:
        """
        Idempotently upsert an ItemChunk using deterministic _id: '{source_id}:{part}'.
        Only overwrites if new content_version >= existing content_version.
        """
        doc = chunk.model_dump(by_alias=True)
        # Conditional update guarding content freshness
        await self.chunks.update_one(
            {"_id": doc["_id"], "$or": [
                {"content_version": {"$lte": doc["content_version"]}},
                {"content_version": {"$exists": False}},
            ]},
            {"$set": doc},
            upsert=True,
        )

    async def delete_item_chunks(self, item_id: str) -> None:
        """Purge all chunks associated with an item."""
        await self.chunks.delete_many({"item_id": item_id})

    async def get_chunk_by_id(self, chunk_id: str) -> Optional[Dict[str, Any]]:
        return await self.chunks.find_one({"_id": chunk_id})

    async def vector_search(
        self,
        query_vector: List[float],
        team_ids: List[str],
        limit: int = 8,
        item_id_scope: Optional[str] = None,
        min_score: float = 0.1,
    ) -> List[Dict[str, Any]]:
        """
        Perform vector retrieval with mandatory team_id pre-filter.
        Tries Atlas Vector Search pipeline; falls back to in-memory cosine ranking if not on Atlas.
        """
        # Build strict pre-filter
        pre_filter: Dict[str, Any] = {"team_id": {"$in": team_ids}}
        if item_id_scope:
            pre_filter["item_id"] = item_id_scope

        # Attempt Atlas Vector Search pipeline
        try:
            pipeline = [
                {
                    "$vectorSearch": {
                        "index": "chunks_vector",
                        "path": "embedding",
                        "queryVector": query_vector,
                        "numCandidates": min(limit * 10, 100),
                        "limit": limit,
                        "filter": pre_filter,
                    }
                },
                {
                    "$project": {
                        "_id": 1,
                        "team_id": 1,
                        "item_id": 1,
                        "item_key": 1,
                        "kind": 1,
                        "source_id": 1,
                        "event_seq": 1,
                        "author_id": 1,
                        "text": 1,
                        "score": {"$meta": "vectorSearchScore"},
                    }
                }
            ]
            cursor = await self.chunks.aggregate(pipeline)
            results = await cursor.to_list(length=limit)
            if results:
                return results
        except Exception:
            # Fallback for local mongo or when Atlas index is building
            pass

        # In-memory similarity fallback
        cursor = self.chunks.find(pre_filter).limit(200)
        docs = await cursor.to_list(length=200)
        scored_docs = []
        for doc in docs:
            emb = doc.get("embedding", [])
            if emb:
                score = cosine_similarity(query_vector, emb)
                if score >= min_score:
                    doc_copy = dict(doc)
                    doc_copy["score"] = round(score, 4)
                    doc_copy.pop("embedding", None)
                    scored_docs.append(doc_copy)

        scored_docs.sort(key=lambda x: x["score"], reverse=True)
        return scored_docs[:limit]

    async def record_ai_query(self, query_data: Dict[str, Any]) -> str:
        """Save audit record in ai_queries collection."""
        res = await self.ai_queries.insert_one(query_data)
        return str(res.inserted_id)
