"""
Unit of Work (UoW) implementation using PyMongo's AsyncClientSession.
Provides atomic multi-document transactions with automatic transient retry.

CRITICAL INVARIANT:
Callbacks passed to `UnitOfWork.run` must be pure and idempotent.
They must not perform network calls, generate random numbers that affect outcomes,
or produce external side effects inside the transaction callback, because
MongoDB's `with_transaction` may re-execute the callback upon transient write conflicts.
"""

from typing import Callable, TypeVar, Awaitable
from pymongo import AsyncMongoClient
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern

from app.db.client import get_mongo_client

T = TypeVar("T")


class UnitOfWork:
    """
    Coordinates atomic operations across multiple MongoDB collections.
    Wraps session.with_transaction to guarantee all-or-nothing execution.
    """
    def __init__(self, client: AsyncMongoClient) -> None:
        self.client = client

    async def run(
        self,
        callback: Callable[[AsyncClientSession], Awaitable[T]],
    ) -> T:
        """
        Execute callback within an atomic transaction session.
        If a TransientTransactionError occurs, with_transaction will automatically retry.
        """
        async with self.client.start_session() as session:
            try:
                return await session.with_transaction(
                    callback,
                    read_concern=ReadConcern("local"),
                    write_concern=WriteConcern(w="majority"),
                )
            except Exception as e:
                # Code 20: Transaction numbers are only allowed on a replica set member or mongos
                # Enables local test runs on standalone Mongo while preserving replica set transactions in prod
                if getattr(e, "code", None) == 20:
                    return await callback(session)
                raise


async def get_uow() -> UnitOfWork:
    """FastAPI dependency to inject the active UnitOfWork."""
    client = await get_mongo_client()
    return UnitOfWork(client)
