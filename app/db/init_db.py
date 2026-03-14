from __future__ import annotations

from sqlalchemy import select

from app.config import settings
from app.db.models import Base, City
from app.db.session import SessionFactory, engine


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    mapping = settings.city_thread_map()
    if not mapping:
        return

    async with SessionFactory() as session:
        for name, thread_id in mapping.items():
            existing = await session.scalar(select(City).where(City.name == name))
            if existing:
                existing.thread_id = thread_id
                existing.is_active = True
            else:
                session.add(City(name=name, thread_id=thread_id, is_active=True))
        await session.commit()

