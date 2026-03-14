from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings


def _make_engine() -> AsyncEngine:
    if settings.database_url.strip():
        url = settings.database_url.strip()
        return create_async_engine(url, pool_pre_ping=True)

    sqlite_path = settings.sqlite_path.strip() or "./apex_cleaning.db"
    return create_async_engine(f"sqlite+aiosqlite:///{sqlite_path}", connect_args={"check_same_thread": False})


engine = _make_engine()
SessionFactory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

