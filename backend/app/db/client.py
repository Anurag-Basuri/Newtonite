"""
MongoDB asynchronous client and database lifecycle management.
Uses PyMongo Async API (AsyncMongoClient) directly per architectural guidelines.
"""

from typing import Optional
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import get_settings, Settings


class MongoManager:
    """Manages the AsyncMongoClient connection lifecycle."""
    def __init__(self) -> None:
        self.client: Optional[AsyncMongoClient] = None

    async def connect(self, settings: Optional[Settings] = None) -> None:
        """Establish the connection pool to MongoDB."""
        if self.client is None:
            cfg = settings or get_settings()
            self.client = AsyncMongoClient(
                cfg.MONGODB_URI,
                maxPoolSize=cfg.MONGO_MAX_POOL,
                minPoolSize=cfg.MONGO_MIN_POOL,
                serverSelectionTimeoutMS=5000,
            )

    async def close(self) -> None:
        """Close connection pool cleanly."""
        if self.client is not None:
            await self.client.close()
            self.client = None

    def get_database(self, settings: Optional[Settings] = None) -> AsyncDatabase:
        """Return the target database."""
        if self.client is None:
            raise RuntimeError("MongoManager is not connected. Call connect() first.")
        cfg = settings or get_settings()
        return self.client[cfg.MONGODB_DB]


# Singleton instance for process-level lifecycle
mongo_manager = MongoManager()


async def get_mongo_client() -> AsyncMongoClient:
    """FastAPI dependency to retrieve the active AsyncMongoClient."""
    if mongo_manager.client is None:
        await mongo_manager.connect()
    assert mongo_manager.client is not None
    return mongo_manager.client


async def get_database() -> AsyncDatabase:
    """FastAPI dependency to retrieve the active AsyncDatabase."""
    if mongo_manager.client is None:
        await mongo_manager.connect()
    return mongo_manager.get_database()
