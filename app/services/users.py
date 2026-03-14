from __future__ import annotations

from aiogram.types import User as TgUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import User, UserRole


async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    return await session.scalar(select(User).where(User.telegram_id == telegram_id))


async def ensure_user(session: AsyncSession, tg_user: TgUser) -> User | None:
    user = await get_user_by_telegram_id(session, tg_user.id)
    username = tg_user.username or ""

    if user:
        if user.username != username:
            user.username = username
            await session.commit()
        return user

    if tg_user.id in settings.admin_ids():
        user = User(telegram_id=tg_user.id, username=username, role=UserRole.admin, is_active=True)
        session.add(user)
        await session.commit()
        return user

    return None


def display_name(user: User) -> str:
    if user.username:
        return f"@{user.username}"
    return str(user.telegram_id)

