from __future__ import annotations

from sqlalchemy import select, text

from app.config import settings
from app.db.models import Base, City
from app.db.session import SessionFactory, engine


async def _ensure_order_columns() -> None:
    """
    Minimal auto-migration for new columns without Alembic.

    - Postgres: ALTER TABLE ... ADD COLUMN IF NOT EXISTS
    - SQLite: check PRAGMA table_info and ADD COLUMN when missing
    """

    async with engine.begin() as conn:
        dialect = conn.dialect.name

        if dialect == "postgresql":
            await conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS cleaning_type VARCHAR(64) NOT NULL DEFAULT ''"))
            await conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS area_sqm NUMERIC(10, 2)"))
            await conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS rooms_count INTEGER"))
            await conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS detergents_on_site BOOLEAN NOT NULL DEFAULT TRUE"))
            await conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS equipment_required TEXT NOT NULL DEFAULT ''"))
            await conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS work_scope TEXT NOT NULL DEFAULT ''"))
            return

        if dialect == "sqlite":
            rows = (await conn.execute(text("PRAGMA table_info('orders')"))).all()
            existing = {r[1] for r in rows}  # (cid, name, type, notnull, dflt_value, pk)

            # Execute sequentially to keep logic simple
            if "cleaning_type" not in existing:
                await conn.execute(text("ALTER TABLE orders ADD COLUMN cleaning_type VARCHAR(64) NOT NULL DEFAULT ''"))
            if "area_sqm" not in existing:
                await conn.execute(text("ALTER TABLE orders ADD COLUMN area_sqm NUMERIC(10, 2)"))
            if "rooms_count" not in existing:
                await conn.execute(text("ALTER TABLE orders ADD COLUMN rooms_count INTEGER"))
            if "detergents_on_site" not in existing:
                await conn.execute(text("ALTER TABLE orders ADD COLUMN detergents_on_site BOOLEAN NOT NULL DEFAULT 1"))
            if "equipment_required" not in existing:
                await conn.execute(text("ALTER TABLE orders ADD COLUMN equipment_required TEXT NOT NULL DEFAULT ''"))
            if "work_scope" not in existing:
                await conn.execute(text("ALTER TABLE orders ADD COLUMN work_scope TEXT NOT NULL DEFAULT ''"))


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await _ensure_order_columns()

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
