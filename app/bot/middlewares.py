from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionFactory


class DbSessionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        async with SessionFactory() as session:
            data["db"] = session
            return await handler(event, data)


def require_db(data: Dict[str, Any]) -> AsyncSession:
    session = data.get("db")
    if session is None:
        raise RuntimeError("DB session missing in handler data")
    return session

