"""Repository for runtime configuration overrides."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from easysql_api.infrastructure.persistence.models import ConfigModel


@dataclass(frozen=True)
class ConfigUpsertItem:
    category: str
    key: str
    value: str
    value_type: str
    is_secret: bool


class ConfigRepository:
    """Persistence operations for runtime configuration overrides."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]):
        self._sessionmaker = sessionmaker

    async def load_all(self) -> list[ConfigModel]:
        async with self._sessionmaker() as db:
            result = await db.execute(
                select(ConfigModel).order_by(ConfigModel.category.asc(), ConfigModel.key.asc())
            )
            return list(result.scalars().all())

    async def upsert_many(self, items: list[ConfigUpsertItem]) -> None:
        if not items:
            return

        payload = [
            {
                "id": uuid.uuid4(),
                "category": item.category,
                "key": item.key,
                "value": item.value,
                "value_type": item.value_type,
                "is_secret": item.is_secret,
            }
            for item in items
        ]

        async with self._sessionmaker() as db:
            stmt = insert(ConfigModel).values(payload)
            stmt = stmt.on_conflict_do_update(
                index_elements=[ConfigModel.category, ConfigModel.key],
                set_={
                    "value": stmt.excluded.value,
                    "value_type": stmt.excluded.value_type,
                    "is_secret": stmt.excluded.is_secret,
                    "updated_at": func.now(),
                },
            )
            await db.execute(stmt)
            await db.commit()

    async def delete_category(self, category: str) -> int:
        async with self._sessionmaker() as db:
            count_result = await db.execute(
                select(func.count())
                .select_from(ConfigModel)
                .where(ConfigModel.category == category)
            )
            deleted = int(count_result.scalar_one())
            if deleted == 0:
                return 0

            await db.execute(delete(ConfigModel).where(ConfigModel.category == category))
            await db.commit()
            return deleted
