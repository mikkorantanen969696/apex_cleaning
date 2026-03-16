from __future__ import annotations

import asyncio
import csv
import logging
from dataclasses import dataclass
from datetime import datetime
from io import StringIO

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import (
    back_to_menu,
    confirm_create_order,
    main_menu_admin,
    main_menu_cleaner,
    main_menu_manager,
    order_actions_kb,
    order_take_button,
    order_taken_button,
    photo_kind_kb,
)
from app.bot.middlewares import DbSessionMiddleware
from app.bot.states import AuthStates, CreateOrderStates, PhotoStates
from app.bot.texts import order_card_text, order_private_details
from app.config import settings
from app.db.init_db import init_db
from app.db.models import City, InviteRole, Order, OrderPhoto, OrderStatus, PhotoKind, User, UserRole
from app.logging_setup import setup_logging
from app.services.invoice import generate_invoice_pdf
from app.services.invites import consume_invite, create_invite
from app.services.orders import (
    create_order_draft,
    get_order_full,
    list_available_orders,
    list_cities,
    list_cleaner_orders,
    list_manager_orders,
    list_recent_orders,
    publish_order,
    safe_decimal,
    take_order_atomic,
    update_order_fields,
)
from app.services.users import ensure_user, get_user_by_telegram_id, list_users_by_role
from app.utils.time import parse_local_datetime


router = Router(name="core")


def _menu_for_role(role: UserRole):
    if role == UserRole.admin:
        return main_menu_admin()
    if role == UserRole.manager:
        return main_menu_manager()
    return main_menu_cleaner()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, db: AsyncSession) -> None:
    await state.clear()

    if not message.from_user:
        await message.answer("Не удалось определить пользователя.")
        return

    user = await ensure_user(db, message.from_user)
    if not user:
        await state.set_state(AuthStates.enter_invite)
        await message.answer(
            "Привет! Чтобы продолжить, введи инвайт-код.\n\n"
            "Если кода нет — попроси администратора создать приглашение."
        )
        return

    await message.answer("Готово. Выбери действие:", reply_markup=_menu_for_role(user.role))


@router.callback_query(F.data == "menu")
async def cb_menu(callback: CallbackQuery, state: FSMContext, db: AsyncSession) -> None:
    await state.clear()
    if not callback.from_user:
        await callback.answer()
        return

    user = await get_user_by_telegram_id(db, callback.from_user.id)
    if not user:
        if callback.message:
            await callback.message.answer("Сначала отправь /start.")
        await callback.answer()
        return

    if callback.message:
        await callback.message.answer("Меню:", reply_markup=_menu_for_role(user.role))
    await callback.answer()


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.message(AuthStates.enter_invite, F.text)
async def auth_invite(message: Message, state: FSMContext, db: AsyncSession) -> None:
    if not message.from_user or not message.text:
        await message.answer("Введи инвайт-код текстом.")
        return

    code = message.text.strip()
    if not code:
        await message.answer("Инвайт-код пустой. Попробуй ещё раз.")
        return

    user = await consume_invite(
        db,
        code=code,
        telegram_user_id=message.from_user.id,
        username=message.from_user.username or "",
    )
    if not user:
        await message.answer("Код не найден или уже использован. Попробуй ещё раз.")
        return

    await state.clear()
    await message.answer("Готово. Ты добавлен(а) в систему.", reply_markup=_menu_for_role(user.role))


@router.message(Command("invite"))
async def cmd_invite(message: Message, db: AsyncSession) -> None:
    """
    /invite manager  -> код для менеджера
    /invite cleaner  -> код для клинера
    """
    if not message.from_user:
        await message.answer("Не удалось определить пользователя.")
        return

    actor = await get_user_by_telegram_id(db, message.from_user.id)
    if not actor or actor.role != UserRole.admin:
        await message.answer("Команда доступна только администратору.")
        return

    parts = (message.text or "").strip().split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /invite manager | /invite cleaner")
        return

    role_raw = parts[1].strip().lower()
    if role_raw == "manager":
        role = InviteRole.manager
    elif role_raw == "cleaner":
        role = InviteRole.cleaner
    else:
        await message.answer("Роль должна быть: manager или cleaner.")
        return

    code = await create_invite(db, role=role, created_by=actor)
    await message.answer(f"Инвайт-код для роли `{role.value}`:\n`{code}`", parse_mode=ParseMode.MARKDOWN)


async def run_bot() -> None:
    setup_logging()

    if not settings.bot_token.strip():
        raise RuntimeError("BOT_TOKEN is empty. Fill it in .env")

    await init_db()

    bot = Bot(
        token=settings.bot_token.strip(),
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.update.middleware(DbSessionMiddleware())
    dp.include_router(router)

    me = await bot.get_me()
    logging.getLogger(__name__).info("Starting bot: @%s (%s)", me.username, me.id)

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


def main() -> None:
    asyncio.run(run_bot())
