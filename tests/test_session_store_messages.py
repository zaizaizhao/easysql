import asyncio
import os
import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from easysql_api.infrastructure.db_manager import ControlPlaneDatabaseManager
from easysql_api.infrastructure.persistence.models import Base
from easysql_api.infrastructure.persistence.session_repository import SqlAlchemySessionRepository


def _normalize_uri(uri: str) -> str:
    if uri.startswith("postgresql+asyncpg://"):
        return uri
    if uri.startswith("postgresql://"):
        return uri.replace("postgresql://", "postgresql+asyncpg://", 1)
    if uri.startswith("postgres://"):
        return uri.replace("postgres://", "postgresql+asyncpg://", 1)
    return uri


def test_session_repository_add_message_and_get():
    uri = os.getenv("POSTGRES_URI")
    if not uri:
        pytest.skip("POSTGRES_URI not set")

    async def _run() -> None:
        engine = create_async_engine(_normalize_uri(uri), pool_pre_ping=True)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        db_manager = ControlPlaneDatabaseManager()
        db_manager._engine = engine
        db_manager._sessionmaker = sessionmaker
        repo = SqlAlchemySessionRepository(db_manager)

        session_id = str(uuid.uuid4())
        session = await repo.create(session_id)
        assert session.session_id == session_id

        message_id = str(uuid.uuid4())
        await repo.add_message(
            session_id=session_id,
            message_id=message_id,
            thread_id=session_id,
            role="user",
            content="hello",
        )

        message = await repo.get_message(message_id)
        assert message is not None
        assert message.message_id == message_id
        assert message.thread_id == session_id

        await repo.delete(session_id)
        await db_manager.dispose()

    asyncio.run(_run())
