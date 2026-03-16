from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import (
    admin_invite_kb,
    back_to_menu,
    cleaning_type_kb,
    confirm_create_order,
    contact_method_kb,
    main_menu_admin,
    main_menu_cleaner,
    main_menu_manager,
    order_actions_kb,
    order_take_button,
    order_taken_button,
    photo_done_kb,
    photo_kind_kb,
    tri_kb,
    yes_no_kb,
)
from app.bot.middlewares import DbSessionMiddleware
from app.bot.states import AdminStates, AuthStates, CreateOrderStates, PhotoStates
from app.bot.texts import order_card_text, order_private_details
from app.config import settings
from app.db.init_db import init_db
from app.db.models import City, InviteRole, OrderPhoto, OrderStatus, PhotoKind, User, UserRole
from app.logging_setup import setup_logging
from app.services.exports import export_orders_csv, export_orders_json
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
from app.services.users import display_name, ensure_user, get_user_by_telegram_id, list_users_by_role
from app.utils.time import parse_local_datetime


router = Router(name="core")


def _role_label(role: UserRole) -> str:
    if role == UserRole.admin:
        return "Администратор"
    if role == UserRole.manager:
        return "Менеджер"
    return "Клинер"


def _menu_for_user(user: User):
    label = _role_label(user.role)
    if not user.is_active:
        label = f"{label} (доступ отключен)"

    if user.role == UserRole.admin:
        return main_menu_admin(label)
    if user.role == UserRole.manager:
        return main_menu_manager(label)
    return main_menu_cleaner(label)


async def _require_actor(db: AsyncSession, tg_user_id: int) -> User | None:
    return await get_user_by_telegram_id(db, tg_user_id)


def _admin_invites_text() -> str:
    return (
        "Приглашения (безопасная выдача ролей):\n"
        "- Менеджер/Клинер получают роль *только* через одноразовый инвайт-код, созданный администратором.\n"
        "- Код действует 72 часа."
    )


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
            "Привет!\n"
            "Твоя роль: *не авторизован*\n\n"
            "Чтобы продолжить, введи инвайт-код.\n\n"
            "Если кода нет — попроси администратора создать приглашение."
        )
        return

    if not user.is_active:
        await message.answer(
            f"Твоя роль: *{_role_label(user.role)}* (доступ отключен).\n"
            "Обратись к администратору.",
            reply_markup=_menu_for_user(user),
        )
        return

    await message.answer(
        f"Готово.\nТвоя роль: *{_role_label(user.role)}*",
        reply_markup=_menu_for_user(user),
    )


@router.message(Command("me"))
async def cmd_me(message: Message, db: AsyncSession) -> None:
    if not message.from_user:
        return
    user = await _require_actor(db, message.from_user.id)
    if not user:
        await message.answer("Твоя роль: *не авторизован*. Нажми /start.")
        return
    await message.answer(
        f"Твоя роль: *{_role_label(user.role)}*{' (доступ отключен)' if not user.is_active else ''}\n"
        f"Telegram ID: `{user.telegram_id}`\n"
        f"Username: `{user.username or '—'}`"
    )


@router.message(Command("help"))
async def cmd_help(message: Message, db: AsyncSession) -> None:
    if not message.from_user:
        return
    user = await _require_actor(db, message.from_user.id)
    role = _role_label(user.role) if user else "не авторизован"
    await message.answer(
        "Команды:\n"
        "- /start — меню и авторизация\n"
        "- /me — показать роль\n"
        "- /invite manager|cleaner — создать инвайт (только админ)\n\n"
        f"Твоя роль: *{role}*"
    )


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
    await message.answer(
        f"Инвайт-код для роли `{role.value}` (одноразовый, действует 72ч):\n`{code}`",
        parse_mode=ParseMode.MARKDOWN,
    )


@router.callback_query(F.data == "admin:managers")
async def cb_admin_managers(callback: CallbackQuery, db: AsyncSession) -> None:
    if not callback.from_user:
        await callback.answer()
        return
    actor = await _require_actor(db, callback.from_user.id)
    if not actor or actor.role != UserRole.admin:
        await callback.answer("Нет доступа", show_alert=True)
        return

    users = await list_users_by_role(db, UserRole.manager, limit=50)
    lines = ["👥 *Менеджеры*"]
    if not users:
        lines.append("— пока никого нет.")
    else:
        for u in users[:30]:
            lines.append(f"- {display_name(u)} • `id:{u.telegram_id}` • {'✅ активен' if u.is_active else '⛔ отключен'}")
    lines.append("")
    lines.append(_admin_invites_text())

    if callback.message:
        await callback.message.answer("\n".join(lines), reply_markup=admin_invite_kb())
    await callback.answer()


@router.callback_query(F.data == "admin:cleaners")
async def cb_admin_cleaners(callback: CallbackQuery, db: AsyncSession) -> None:
    if not callback.from_user:
        await callback.answer()
        return
    actor = await _require_actor(db, callback.from_user.id)
    if not actor or actor.role != UserRole.admin:
        await callback.answer("Нет доступа", show_alert=True)
        return

    users = await list_users_by_role(db, UserRole.cleaner, limit=50)
    lines = ["🧹 *Клинеры*"]
    if not users:
        lines.append("— пока никого нет.")
    else:
        for u in users[:30]:
            lines.append(f"- {display_name(u)} • `id:{u.telegram_id}` • {'✅ активен' if u.is_active else '⛔ отключен'}")
    lines.append("")
    lines.append(_admin_invites_text())

    if callback.message:
        await callback.message.answer("\n".join(lines), reply_markup=admin_invite_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("admin:invite:"))
async def cb_admin_invite(callback: CallbackQuery, db: AsyncSession) -> None:
    if not callback.from_user:
        await callback.answer()
        return
    actor = await _require_actor(db, callback.from_user.id)
    if not actor or actor.role != UserRole.admin:
        await callback.answer("Нет доступа", show_alert=True)
        return

    role_raw = callback.data.split(":", 2)[2]
    role = InviteRole.manager if role_raw == "manager" else InviteRole.cleaner
    code = await create_invite(db, role=role, created_by=actor)
    if callback.message:
        await callback.message.answer(f"Инвайт-код для роли `{role.value}` (одноразовый, 72ч):\n`{code}`")
    await callback.answer("Готово")


@router.callback_query(F.data == "admin:cities")
async def cb_admin_cities(callback: CallbackQuery, state: FSMContext, db: AsyncSession) -> None:
    if not callback.from_user:
        await callback.answer()
        return
    actor = await _require_actor(db, callback.from_user.id)
    if not actor or actor.role != UserRole.admin:
        await callback.answer("Нет доступа", show_alert=True)
        return

    await state.clear()
    cities = (await db.scalars(select(City).order_by(City.name.asc()))).all()
    lines = ["🏙 *Города/темы*"]
    if not cities:
        lines.append("— городов нет. Добавь: `Название=thread_id`")
    else:
        for c in cities[:50]:
            lines.append(f"- {c.name} = `{c.thread_id}` • {'✅ активен' if c.is_active else '⛔ отключен'}")
    lines.append("")
    lines.append("Чтобы добавить/обновить город, отправь строку вида: `Название=123`")

    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить/обновить", callback_data="admin:city:add")
    kb.button(text="⬅️ В меню", callback_data="menu")
    kb.adjust(1, 1)
    if callback.message:
        await callback.message.answer("\n".join(lines), reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data == "admin:city:add")
async def cb_admin_city_add(callback: CallbackQuery, state: FSMContext, db: AsyncSession) -> None:
    if not callback.from_user:
        await callback.answer()
        return
    actor = await _require_actor(db, callback.from_user.id)
    if not actor or actor.role != UserRole.admin:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.set_state(AdminStates.add_or_update_city)
    if callback.message:
        await callback.message.answer("Отправь: `Название=thread_id` (например: `Краснодар=27`).", reply_markup=back_to_menu())
    await callback.answer()


@router.message(AdminStates.add_or_update_city, F.text)
async def admin_city_upsert(message: Message, state: FSMContext, db: AsyncSession) -> None:
    if not message.from_user or not message.text:
        return
    actor = await _require_actor(db, message.from_user.id)
    if not actor or actor.role != UserRole.admin:
        await message.answer("Недостаточно прав.")
        return

    raw = message.text.strip()
    if "=" not in raw:
        await message.answer("Неверный формат. Нужно: `Название=thread_id`")
        return
    name, thread_id_raw = raw.split("=", 1)
    name = name.strip()
    thread_id_raw = thread_id_raw.strip()
    if not name or not thread_id_raw.isdigit():
        await message.answer("Неверный формат. Пример: `Краснодар=27`")
        return

    thread_id = int(thread_id_raw)
    city = await db.scalar(select(City).where(City.name == name))
    if city:
        city.thread_id = thread_id
        city.is_active = True
    else:
        db.add(City(name=name, thread_id=thread_id, is_active=True))
    await db.commit()
    await state.clear()
    await message.answer("Готово. Город сохранён.", reply_markup=back_to_menu())


@router.callback_query(F.data == "admin:orders")
async def cb_admin_orders(callback: CallbackQuery, db: AsyncSession) -> None:
    if not callback.from_user:
        await callback.answer()
        return
    actor = await _require_actor(db, callback.from_user.id)
    if not actor or actor.role != UserRole.admin:
        await callback.answer("Нет доступа", show_alert=True)
        return

    orders = await list_recent_orders(db, limit=20)
    if callback.message:
        if not orders:
            await callback.message.answer("Заявок пока нет.", reply_markup=back_to_menu())
        else:
            await callback.message.answer("🧾 *Последние заявки:*", reply_markup=_orders_list_kb(orders).as_markup())
    await callback.answer()


@router.callback_query(F.data == "admin:export")
async def cb_admin_export_menu(callback: CallbackQuery, db: AsyncSession) -> None:
    if not callback.from_user:
        await callback.answer()
        return
    actor = await _require_actor(db, callback.from_user.id)
    if not actor or actor.role != UserRole.admin:
        await callback.answer("Нет доступа", show_alert=True)
        return

    kb = InlineKeyboardBuilder()
    kb.button(text="📄 CSV (все заявки)", callback_data="admin:export:csv")
    kb.button(text="🧾 JSON (все заявки)", callback_data="admin:export:json")
    kb.button(text="⬅️ В меню", callback_data="menu")
    kb.adjust(1, 1, 1)
    if callback.message:
        await callback.message.answer("Экспорт заявок:", reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("admin:export:"))
async def cb_admin_export(callback: CallbackQuery, bot: Bot, db: AsyncSession) -> None:
    if not callback.from_user:
        await callback.answer()
        return
    actor = await _require_actor(db, callback.from_user.id)
    if not actor or actor.role != UserRole.admin:
        await callback.answer("Нет доступа", show_alert=True)
        return

    kind = callback.data.split(":", 2)[2]
    export = await (export_orders_csv(db) if kind == "csv" else export_orders_json(db))
    await bot.send_document(
        chat_id=callback.from_user.id,
        document=BufferedInputFile(export.content, filename=export.filename),
        caption=f"Экспорт ({kind.upper()})",
    )
    await callback.answer("Файл отправлен")


@router.callback_query(F.data == "mgr:export")
async def cb_mgr_export(callback: CallbackQuery, bot: Bot, db: AsyncSession) -> None:
    if not callback.from_user:
        await callback.answer()
        return
    actor = await _require_actor(db, callback.from_user.id)
    if not actor or actor.role not in (UserRole.manager, UserRole.admin) or not actor.is_active:
        await callback.answer("Нет доступа", show_alert=True)
        return

    export = await export_orders_csv(db, manager_user_id=actor.id)
    await bot.send_document(
        chat_id=callback.from_user.id,
        document=BufferedInputFile(export.content, filename=export.filename),
        caption="Только твои заявки (CSV)",
    )
    await callback.answer("Готово")


@router.callback_query(F.data == "mgr:my_orders")
async def cb_mgr_my_orders(callback: CallbackQuery, db: AsyncSession) -> None:
    if not callback.from_user:
        await callback.answer()
        return
    actor = await _require_actor(db, callback.from_user.id)
    if not actor or actor.role not in (UserRole.manager, UserRole.admin) or not actor.is_active:
        await callback.answer("Нет доступа", show_alert=True)
        return

    orders = await list_manager_orders(db, actor.id, limit=20)
    if callback.message:
        if not orders:
            await callback.message.answer("У тебя пока нет заявок.", reply_markup=back_to_menu())
        else:
            await callback.message.answer("🧾 *Твои заявки:*", reply_markup=_orders_list_kb(orders).as_markup())
    await callback.answer()


@router.callback_query(F.data == "mgr:invoice")
async def cb_mgr_invoice_menu(callback: CallbackQuery, db: AsyncSession) -> None:
    if not callback.from_user:
        await callback.answer()
        return
    actor = await _require_actor(db, callback.from_user.id)
    if not actor or actor.role not in (UserRole.manager, UserRole.admin) or not actor.is_active:
        await callback.answer("Нет доступа", show_alert=True)
        return

    orders = await list_manager_orders(db, actor.id, limit=10)
    if callback.message:
        if not orders:
            await callback.message.answer("Нет заявок для счета.", reply_markup=back_to_menu())
        else:
            kb = InlineKeyboardBuilder()
            for o in orders:
                kb.button(text=f"{o.public_id}", callback_data=f"invoice:order:{o.id}")
            kb.button(text="⬅️ В меню", callback_data="menu")
            kb.adjust(1, 1, 1, 1, 1)
            await callback.message.answer("Выбери заявку для счета:", reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data == "mgr:create_order")
async def cb_mgr_create_order(callback: CallbackQuery, state: FSMContext, db: AsyncSession) -> None:
    if not callback.from_user:
        await callback.answer()
        return
    actor = await _require_actor(db, callback.from_user.id)
    if not actor or actor.role not in (UserRole.manager, UserRole.admin) or not actor.is_active:
        await callback.answer("Нет доступа", show_alert=True)
        return

    await state.clear()
    await state.set_state(CreateOrderStates.choose_city)
    cities = await list_cities(db)
    if callback.message:
        if not cities:
            await callback.message.answer("Нет активных городов. Админ должен настроить CITY_THREADS или добавить город.", reply_markup=back_to_menu())
        else:
            await callback.message.answer("Выбери город:", reply_markup=_cities_kb(cities).as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("mgr:city:"))
async def cb_mgr_choose_city(callback: CallbackQuery, state: FSMContext, db: AsyncSession) -> None:
    if not callback.from_user:
        await callback.answer()
        return
    actor = await _require_actor(db, callback.from_user.id)
    if not actor or actor.role not in (UserRole.manager, UserRole.admin) or not actor.is_active:
        await callback.answer("Нет доступа", show_alert=True)
        return

    city_id = int(callback.data.split(":")[2])
    city = await db.scalar(select(City).where(City.id == city_id, City.is_active.is_(True)))
    if not city:
        await callback.answer("Город не найден", show_alert=True)
        return

    order = await create_order_draft(db, manager=actor, city=city)
    await state.update_data(order_id=order.id)
    await state.set_state(CreateOrderStates.service_type)
    if callback.message:
        await callback.message.answer(
            f"Заявка *{order.public_id}* создана (черновик).\n"
            f"Город: *{city.name}*\n\n"
            "Выбери тип объекта/услуги:",
            reply_markup=_service_type_kb().as_markup(),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("mgr:service_type:"))
async def cb_mgr_service_type(callback: CallbackQuery, state: FSMContext, db: AsyncSession) -> None:
    if not callback.from_user:
        await callback.answer()
        return
    actor = await _require_actor(db, callback.from_user.id)
    if not actor or actor.role not in (UserRole.manager, UserRole.admin) or not actor.is_active:
        await callback.answer("Нет доступа", show_alert=True)
        return

    value = callback.data.split(":", 2)[2]
    if value == "__other__":
        await state.set_state(CreateOrderStates.service_type)
        await state.update_data(expect_service_type_text=True)
        if callback.message:
            await callback.message.answer("Напиши тип объекта/услуги текстом (например: `Коттедж 2 этажа`).")
        await callback.answer()
        return

    data = await state.get_data()
    order_id = data.get("order_id")
    if not order_id:
        await callback.answer("Черновик не найден. Нажми /start", show_alert=True)
        return

    await update_order_fields(db, order_id, service_type=value)
    await state.set_state(CreateOrderStates.cleaning_type)
    if callback.message:
        await callback.message.answer("Выбери тип уборки:", reply_markup=cleaning_type_kb())
    await callback.answer()


@router.message(CreateOrderStates.service_type, F.text)
async def msg_mgr_service_type(message: Message, state: FSMContext, db: AsyncSession) -> None:
    if not message.from_user or not message.text:
        return
    actor = await _require_actor(db, message.from_user.id)
    if not actor or actor.role not in (UserRole.manager, UserRole.admin) or not actor.is_active:
        await message.answer("Недостаточно прав.")
        return

    data = await state.get_data()
    order_id = data.get("order_id")
    if not order_id:
        await message.answer("Черновик не найден. Нажми /start.")
        return

    value = message.text.strip()
    if not value:
        await message.answer("Напиши значение текстом.")
        return

    await update_order_fields(db, order_id, service_type=value)
    await state.set_state(CreateOrderStates.cleaning_type)
    await message.answer("Выбери тип уборки:", reply_markup=cleaning_type_kb())


@router.callback_query(F.data == "mgr:back:service_type")
async def cb_mgr_back_service_type(callback: CallbackQuery, state: FSMContext, db: AsyncSession) -> None:
    if not callback.from_user:
        await callback.answer()
        return
    actor = await _require_actor(db, callback.from_user.id)
    if not actor or actor.role not in (UserRole.manager, UserRole.admin) or not actor.is_active:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.set_state(CreateOrderStates.service_type)
    if callback.message:
        await callback.message.answer("Выбери тип объекта/услуги:", reply_markup=_service_type_kb().as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("mgr:cleaning_type:"))
async def cb_mgr_cleaning_type(callback: CallbackQuery, state: FSMContext, db: AsyncSession) -> None:
    if not callback.from_user:
        await callback.answer()
        return
    actor = await _require_actor(db, callback.from_user.id)
    if not actor or actor.role not in (UserRole.manager, UserRole.admin) or not actor.is_active:
        await callback.answer("Нет доступа", show_alert=True)
        return

    value = callback.data.split(":", 2)[2]
    data = await state.get_data()
    order_id = data.get("order_id")
    if not order_id:
        await callback.answer("Черновик не найден", show_alert=True)
        return

    await update_order_fields(db, order_id, cleaning_type=value)
    await state.set_state(CreateOrderStates.address)
    if callback.message:
        await callback.message.answer("Введи адрес (как в реальном мире, с домом/кв/подъездом):")
    await callback.answer()


@router.message(CreateOrderStates.address, F.text)
async def msg_mgr_address(message: Message, state: FSMContext, db: AsyncSession) -> None:
    if not message.from_user or not message.text:
        return
    actor = await _require_actor(db, message.from_user.id)
    if not actor or actor.role not in (UserRole.manager, UserRole.admin) or not actor.is_active:
        await message.answer("Недостаточно прав.")
        return

    data = await state.get_data()
    order_id = data.get("order_id")
    if not order_id:
        await message.answer("Черновик не найден. Нажми /start.")
        return

    value = message.text.strip()
    if len(value) < 6:
        await message.answer("Адрес слишком короткий. Попробуй ещё раз.")
        return

    await update_order_fields(db, order_id, address=value)
    await state.set_state(CreateOrderStates.scheduled_at)
    await message.answer("Введи дату и время приезда: `дд.мм.гггг чч:мм` (например: `17.03.2026 14:30`).")


@router.message(CreateOrderStates.scheduled_at, F.text)
async def msg_mgr_scheduled_at(message: Message, state: FSMContext, db: AsyncSession) -> None:
    if not message.from_user or not message.text:
        return
    actor = await _require_actor(db, message.from_user.id)
    if not actor or actor.role not in (UserRole.manager, UserRole.admin) or not actor.is_active:
        await message.answer("Недостаточно прав.")
        return

    dt = parse_local_datetime(message.text)
    if not dt:
        await message.answer("Не понял дату/время. Формат: `дд.мм.гггг чч:мм`")
        return

    data = await state.get_data()
    order_id = data.get("order_id")
    if not order_id:
        await message.answer("Черновик не найден.")
        return

    await update_order_fields(db, order_id, scheduled_at=dt)
    await state.set_state(CreateOrderStates.area_sqm)
    await message.answer("Площадь, м² (например: `54`).")


@router.message(CreateOrderStates.area_sqm, F.text)
async def msg_mgr_area(message: Message, state: FSMContext, db: AsyncSession) -> None:
    if not message.from_user or not message.text:
        return
    actor = await _require_actor(db, message.from_user.id)
    if not actor or actor.role not in (UserRole.manager, UserRole.admin) or not actor.is_active:
        await message.answer("Недостаточно прав.")
        return

    dec = safe_decimal(message.text)
    if dec is None or dec <= 0:
        await message.answer("Нужно число > 0 (например: `54`).")
        return

    data = await state.get_data()
    order_id = data.get("order_id")
    await update_order_fields(db, order_id, area_sqm=float(dec))
    await state.set_state(CreateOrderStates.rooms_count)
    await message.answer("Количество комнат (например: `2`). Если студия — `1`.")


@router.message(CreateOrderStates.rooms_count, F.text)
async def msg_mgr_rooms(message: Message, state: FSMContext, db: AsyncSession) -> None:
    if not message.from_user or not message.text:
        return
    actor = await _require_actor(db, message.from_user.id)
    if not actor or actor.role not in (UserRole.manager, UserRole.admin) or not actor.is_active:
        await message.answer("Недостаточно прав.")
        return

    raw = message.text.strip()
    if not raw.isdigit():
        await message.answer("Нужно целое число (например: `2`).")
        return
    value = int(raw)
    if value <= 0 or value > 30:
        await message.answer("Проверь значение. Обычно 1..30.")
        return

    data = await state.get_data()
    order_id = data.get("order_id")
    await update_order_fields(db, order_id, rooms_count=value)
    await state.set_state(CreateOrderStates.bathrooms_count)
    await message.answer("Количество санузлов (например: `1`).")


@router.message(CreateOrderStates.bathrooms_count, F.text)
async def msg_mgr_baths(message: Message, state: FSMContext, db: AsyncSession) -> None:
    if not message.from_user or not message.text:
        return
    actor = await _require_actor(db, message.from_user.id)
    if not actor or actor.role not in (UserRole.manager, UserRole.admin) or not actor.is_active:
        await message.answer("Недостаточно прав.")
        return

    raw = message.text.strip()
    if not raw.isdigit():
        await message.answer("Нужно целое число (например: `1`).")
        return
    value = int(raw)
    if value <= 0 or value > 20:
        await message.answer("Проверь значение. Обычно 1..20.")
        return

    data = await state.get_data()
    order_id = data.get("order_id")
    await update_order_fields(db, order_id, bathrooms_count=value)
    await state.set_state(CreateOrderStates.detergents_on_site)
    await message.answer("Моющие средства на месте?", reply_markup=yes_no_kb("mgr:detergents:1", "mgr:detergents:0"))


@router.callback_query(F.data.startswith("mgr:detergents:"))
async def cb_mgr_detergents(callback: CallbackQuery, state: FSMContext, db: AsyncSession) -> None:
    if not callback.from_user:
        await callback.answer()
        return
    actor = await _require_actor(db, callback.from_user.id)
    if not actor or actor.role not in (UserRole.manager, UserRole.admin) or not actor.is_active:
        await callback.answer("Нет доступа", show_alert=True)
        return

    value = callback.data.split(":", 2)[2] == "1"
    data = await state.get_data()
    order_id = data.get("order_id")
    await update_order_fields(db, order_id, detergents_on_site=value)
    await state.set_state(CreateOrderStates.vacuum_on_site)
    if callback.message:
        await callback.message.answer("Пылесос на месте?", reply_markup=tri_kb("mgr:vacuum:1", "mgr:vacuum:0", "mgr:vacuum:u"))
    await callback.answer()


@router.callback_query(F.data.startswith("mgr:vacuum:"))
async def cb_mgr_vacuum(callback: CallbackQuery, state: FSMContext, db: AsyncSession) -> None:
    if not callback.from_user:
        await callback.answer()
        return
    actor = await _require_actor(db, callback.from_user.id)
    if not actor or actor.role not in (UserRole.manager, UserRole.admin) or not actor.is_active:
        await callback.answer("Нет доступа", show_alert=True)
        return

    raw = callback.data.split(":", 2)[2]
    value = None if raw == "u" else (raw == "1")
    data = await state.get_data()
    order_id = data.get("order_id")
    await update_order_fields(db, order_id, vacuum_on_site=value)
    await state.set_state(CreateOrderStates.ladder_on_site)
    if callback.message:
        await callback.message.answer("Стремянка на месте?", reply_markup=tri_kb("mgr:ladder:1", "mgr:ladder:0", "mgr:ladder:u"))
    await callback.answer()


@router.callback_query(F.data.startswith("mgr:ladder:"))
async def cb_mgr_ladder(callback: CallbackQuery, state: FSMContext, db: AsyncSession) -> None:
    if not callback.from_user:
        await callback.answer()
        return
    actor = await _require_actor(db, callback.from_user.id)
    if not actor or actor.role not in (UserRole.manager, UserRole.admin) or not actor.is_active:
        await callback.answer("Нет доступа", show_alert=True)
        return

    raw = callback.data.split(":", 2)[2]
    value = None if raw == "u" else (raw == "1")
    data = await state.get_data()
    order_id = data.get("order_id")
    await update_order_fields(db, order_id, ladder_on_site=value)
    await state.set_state(CreateOrderStates.equipment_required)
    if callback.message:
        await callback.message.answer("Оборудование/инвентарь нужно привезти? Если нет — напиши `нет`.")
    await callback.answer()


@router.message(CreateOrderStates.equipment_required, F.text)
async def msg_mgr_equipment(message: Message, state: FSMContext, db: AsyncSession) -> None:
    if not message.from_user or not message.text:
        return
    actor = await _require_actor(db, message.from_user.id)
    if not actor or actor.role not in (UserRole.manager, UserRole.admin) or not actor.is_active:
        await message.answer("Недостаточно прав.")
        return

    value = message.text.strip()
    if value.lower() in ("нет", "не нужно", "-"):
        value = ""

    data = await state.get_data()
    order_id = data.get("order_id")
    await update_order_fields(db, order_id, equipment_required=value)
    await state.set_state(CreateOrderStates.work_scope)
    await message.answer("Объём работ (списком): что именно нужно сделать?")


@router.message(CreateOrderStates.work_scope, F.text)
async def msg_mgr_work_scope(message: Message, state: FSMContext, db: AsyncSession) -> None:
    if not message.from_user or not message.text:
        return
    actor = await _require_actor(db, message.from_user.id)
    if not actor or actor.role not in (UserRole.manager, UserRole.admin) or not actor.is_active:
        await message.answer("Недостаточно прав.")
        return

    value = message.text.strip()
    if len(value) < 3:
        await message.answer("Опиши объём работ подробнее.")
        return

    data = await state.get_data()
    order_id = data.get("order_id")
    await update_order_fields(db, order_id, work_scope=value)
    await state.set_state(CreateOrderStates.access_notes)
    await message.answer("Доступ/парковка/этаж/код домофона/пропуск — всё важное (если нет — `-`).")


@router.message(CreateOrderStates.access_notes, F.text)
async def msg_mgr_access_notes(message: Message, state: FSMContext, db: AsyncSession) -> None:
    if not message.from_user or not message.text:
        return
    actor = await _require_actor(db, message.from_user.id)
    if not actor or actor.role not in (UserRole.manager, UserRole.admin) or not actor.is_active:
        await message.answer("Недостаточно прав.")
        return

    value = message.text.strip()
    if value == "-":
        value = ""

    data = await state.get_data()
    order_id = data.get("order_id")
    await update_order_fields(db, order_id, access_notes=value)
    await state.set_state(CreateOrderStates.client_name)
    await message.answer("Имя клиента:")


@router.message(CreateOrderStates.client_name, F.text)
async def msg_mgr_client_name(message: Message, state: FSMContext, db: AsyncSession) -> None:
    if not message.from_user or not message.text:
        return
    actor = await _require_actor(db, message.from_user.id)
    if not actor or actor.role not in (UserRole.manager, UserRole.admin) or not actor.is_active:
        await message.answer("Недостаточно прав.")
        return

    value = message.text.strip()
    if len(value) < 2:
        await message.answer("Слишком коротко. Попробуй ещё раз.")
        return

    data = await state.get_data()
    order_id = data.get("order_id")
    await update_order_fields(db, order_id, client_name=value)
    await state.set_state(CreateOrderStates.client_phone)
    await message.answer("Телефон клиента (например: `+79991234567`).")


@router.message(CreateOrderStates.client_phone, F.text)
async def msg_mgr_client_phone(message: Message, state: FSMContext, db: AsyncSession) -> None:
    if not message.from_user or not message.text:
        return
    actor = await _require_actor(db, message.from_user.id)
    if not actor or actor.role not in (UserRole.manager, UserRole.admin) or not actor.is_active:
        await message.answer("Недостаточно прав.")
        return

    phone = message.text.strip()
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) < 10:
        await message.answer("Телефон выглядит некорректно. Попробуй ещё раз.")
        return

    data = await state.get_data()
    order_id = data.get("order_id")
    await update_order_fields(db, order_id, client_phone=phone)
    await state.set_state(CreateOrderStates.client_contact_method)
    await message.answer("Предпочтительный способ связи:", reply_markup=contact_method_kb())


@router.callback_query(F.data == "mgr:back:client_phone")
async def cb_mgr_back_client_phone(callback: CallbackQuery, state: FSMContext, db: AsyncSession) -> None:
    if not callback.from_user:
        await callback.answer()
        return
    actor = await _require_actor(db, callback.from_user.id)
    if not actor or actor.role not in (UserRole.manager, UserRole.admin) or not actor.is_active:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.set_state(CreateOrderStates.client_phone)
    if callback.message:
        await callback.message.answer("Телефон клиента (например: `+79991234567`).")
    await callback.answer()


@router.callback_query(F.data.startswith("mgr:contact_method:"))
async def cb_mgr_contact_method(callback: CallbackQuery, state: FSMContext, db: AsyncSession) -> None:
    if not callback.from_user:
        await callback.answer()
        return
    actor = await _require_actor(db, callback.from_user.id)
    if not actor or actor.role not in (UserRole.manager, UserRole.admin) or not actor.is_active:
        await callback.answer("Нет доступа", show_alert=True)
        return

    method = callback.data.split(":", 2)[2]
    data = await state.get_data()
    order_id = data.get("order_id")
    await update_order_fields(db, order_id, client_contact_method=method)
    await state.set_state(CreateOrderStates.price)
    if callback.message:
        await callback.message.answer("Цена для клиента, ₽ (например: `3500`).")
    await callback.answer()


@router.message(CreateOrderStates.price, F.text)
async def msg_mgr_price(message: Message, state: FSMContext, db: AsyncSession) -> None:
    if not message.from_user or not message.text:
        return
    actor = await _require_actor(db, message.from_user.id)
    if not actor or actor.role not in (UserRole.manager, UserRole.admin) or not actor.is_active:
        await message.answer("Недостаточно прав.")
        return

    dec = safe_decimal(message.text)
    if dec is None or dec <= 0:
        await message.answer("Нужно число > 0 (например: `3500`).")
        return

    data = await state.get_data()
    order_id = data.get("order_id")
    await update_order_fields(db, order_id, price_client=float(dec))
    await state.set_state(CreateOrderStates.comment)
    await message.answer("Комментарий (опционально). Если нет — отправь `-`.")


@router.message(CreateOrderStates.comment, F.text)
async def msg_mgr_comment(message: Message, state: FSMContext, db: AsyncSession) -> None:
    if not message.from_user or not message.text:
        return
    actor = await _require_actor(db, message.from_user.id)
    if not actor or actor.role not in (UserRole.manager, UserRole.admin) or not actor.is_active:
        await message.answer("Недостаточно прав.")
        return

    value = message.text.strip()
    if value == "-":
        value = ""

    data = await state.get_data()
    order_id = data.get("order_id")
    await update_order_fields(db, order_id, comment=value)
    await state.set_state(CreateOrderStates.confirm)

    order = await get_order_full(db, order_id)
    if not order:
        await message.answer("Черновик не найден.")
        return

    await message.answer("Проверь заявку перед публикацией:\n\n" + order_private_details(order), reply_markup=confirm_create_order())


@router.callback_query(F.data == "mgr:cancel_create")
async def cb_mgr_cancel_create(callback: CallbackQuery, state: FSMContext, db: AsyncSession) -> None:
    if not callback.from_user:
        await callback.answer()
        return
    actor = await _require_actor(db, callback.from_user.id)
    if not actor or actor.role not in (UserRole.manager, UserRole.admin) or not actor.is_active:
        await callback.answer("Нет доступа", show_alert=True)
        return

    data = await state.get_data()
    order_id = data.get("order_id")
    if order_id:
        await update_order_fields(db, order_id, status=OrderStatus.canceled)
    await state.clear()
    if callback.message:
        await callback.message.answer("Черновик отменён.", reply_markup=back_to_menu())
    await callback.answer("Ок")


@router.callback_query(F.data == "mgr:publish_order")
async def cb_mgr_publish_order(callback: CallbackQuery, state: FSMContext, bot: Bot, db: AsyncSession) -> None:
    if not callback.from_user:
        await callback.answer()
        return
    actor = await _require_actor(db, callback.from_user.id)
    if not actor or actor.role not in (UserRole.manager, UserRole.admin) or not actor.is_active:
        await callback.answer("Нет доступа", show_alert=True)
        return

    data = await state.get_data()
    order_id = data.get("order_id")
    if not order_id:
        await callback.answer("Черновик не найден", show_alert=True)
        return

    order = await get_order_full(db, order_id)
    if not order:
        await callback.answer("Черновик не найден", show_alert=True)
        return

    if not settings.supergroup_chat_id:
        if callback.message:
            await callback.message.answer("SUPERGROUP_CHAT_ID не настроен. Админ должен настроить публикацию.")
        await callback.answer()
        return

    if not order.city or not order.city.thread_id:
        if callback.message:
            await callback.message.answer("Для города не настроен thread_id. Админ должен настроить город/тему.")
        await callback.answer()
        return

    msg = await bot.send_message(
        chat_id=settings.supergroup_chat_id,
        message_thread_id=order.city.thread_id,
        text=order_card_text(order),
        reply_markup=order_take_button(order.id),
    )
    await publish_order(db, order.id, published_message_id=msg.message_id)
    await state.clear()

    if callback.message:
        await callback.message.answer(f"Опубликовано: *{order.public_id}*.\nТвоя роль: *{_role_label(actor.role)}*", reply_markup=back_to_menu())
    await callback.answer("Опубликовано")


@router.callback_query(F.data == "cln:available")
async def cb_cln_available(callback: CallbackQuery, db: AsyncSession) -> None:
    if not callback.from_user:
        await callback.answer()
        return
    actor = await _require_actor(db, callback.from_user.id)
    if not actor or actor.role != UserRole.cleaner or not actor.is_active:
        await callback.answer("Нет доступа", show_alert=True)
        return

    orders = await list_available_orders(db, limit=10)
    if callback.message:
        if not orders:
            await callback.message.answer("Доступных заявок пока нет.", reply_markup=back_to_menu())
        else:
            await callback.message.answer(f"Доступные заявки.\nТвоя роль: *{_role_label(actor.role)}*")
            for o in orders:
                full = await get_order_full(db, o.id)
                if not full:
                    continue
                await callback.message.answer(order_card_text(full), reply_markup=order_take_button(full.id))
    await callback.answer()


@router.callback_query(F.data == "cln:my_orders")
async def cb_cln_my_orders(callback: CallbackQuery, db: AsyncSession) -> None:
    if not callback.from_user:
        await callback.answer()
        return
    actor = await _require_actor(db, callback.from_user.id)
    if not actor or actor.role != UserRole.cleaner or not actor.is_active:
        await callback.answer("Нет доступа", show_alert=True)
        return

    orders = await list_cleaner_orders(db, actor.id, limit=20)
    if callback.message:
        if not orders:
            await callback.message.answer("У тебя пока нет заказов.", reply_markup=back_to_menu())
        else:
            await callback.message.answer("🧾 *Твои заказы:*", reply_markup=_orders_list_kb(orders).as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("order:open:"))
async def cb_order_open(callback: CallbackQuery, db: AsyncSession) -> None:
    if not callback.from_user:
        await callback.answer()
        return

    actor = await _require_actor(db, callback.from_user.id)
    if not actor or not actor.is_active:
        await callback.answer("Сначала авторизуйся (/start)", show_alert=True)
        return

    order_id = int(callback.data.split(":")[2])
    order = await get_order_full(db, order_id)
    if not order:
        await callback.answer("Заявка не найдена", show_alert=True)
        return

    is_admin = actor.role == UserRole.admin
    is_manager = is_admin or (actor.role == UserRole.manager and order.manager_id == actor.id)
    is_cleaner = actor.role == UserRole.cleaner and order.cleaner_id == actor.id
    if not (is_manager or is_cleaner):
        await callback.answer("Нет доступа к заявке", show_alert=True)
        return

    if callback.message:
        await callback.message.answer(
            order_private_details(order),
            reply_markup=order_actions_kb(order.id, is_manager=is_manager, is_cleaner=is_cleaner),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("order:take:"))
async def cb_order_take(callback: CallbackQuery, bot: Bot, db: AsyncSession) -> None:
    if not callback.from_user:
        await callback.answer()
        return

    actor = await _require_actor(db, callback.from_user.id)
    if not actor or actor.role != UserRole.cleaner or not actor.is_active:
        await callback.answer("Нет доступа", show_alert=True)
        return

    order_id = int(callback.data.split(":")[2])
    order = await take_order_atomic(db, order_id=order_id, cleaner=actor)
    if not order:
        await callback.answer("Уже занято или недоступно", show_alert=True)
        if callback.message:
            try:
                await callback.message.edit_reply_markup(reply_markup=order_taken_button())
            except Exception:
                pass
        return

    if callback.message:
        try:
            await callback.message.edit_reply_markup(reply_markup=order_taken_button())
        except Exception:
            pass

    full = await get_order_full(db, order_id)
    if full:
        await bot.send_message(
            chat_id=actor.telegram_id,
            text="✅ Ты взял(а) заказ.\n\n" + order_private_details(full),
            reply_markup=order_actions_kb(full.id, is_manager=False, is_cleaner=True),
        )
        if full.manager:
            await bot.send_message(
                chat_id=full.manager.telegram_id,
                text=f"✅ Заказ *{full.public_id}* взят клинером: {display_name(actor)}",
            )

    await callback.answer("Заказ взят")


@router.callback_query(F.data.startswith("order:status:"))
async def cb_order_status(callback: CallbackQuery, bot: Bot, db: AsyncSession) -> None:
    if not callback.from_user:
        await callback.answer()
        return
    actor = await _require_actor(db, callback.from_user.id)
    if not actor or actor.role != UserRole.cleaner or not actor.is_active:
        await callback.answer("Нет доступа", show_alert=True)
        return

    _, _, order_id_raw, status_raw = callback.data.split(":", 3)
    order_id = int(order_id_raw)
    try:
        status = OrderStatus(status_raw)
    except Exception:
        await callback.answer("Недопустимый статус", show_alert=True)
        return

    full = await get_order_full(db, order_id)
    if not full or full.cleaner_id != actor.id:
        await callback.answer("Нет доступа к заявке", show_alert=True)
        return

    if status not in (OrderStatus.in_progress, OrderStatus.done):
        await callback.answer("Недопустимый статус", show_alert=True)
        return

    await update_order_fields(db, order_id, status=status)
    if callback.message:
        await callback.message.answer(f"Статус обновлён: *{status.value}*")
    if full.manager:
        try:
            await bot.send_message(chat_id=full.manager.telegram_id, text=f"🚧 Статус *{full.public_id}*: `{status.value}`")
        except Exception:
            pass
    await callback.answer("Ок")


@router.callback_query(F.data.startswith("order:cancel:"))
async def cb_order_cancel(callback: CallbackQuery, bot: Bot, db: AsyncSession) -> None:
    if not callback.from_user:
        await callback.answer()
        return
    actor = await _require_actor(db, callback.from_user.id)
    if not actor or actor.role not in (UserRole.manager, UserRole.admin) or not actor.is_active:
        await callback.answer("Нет доступа", show_alert=True)
        return

    order_id = int(callback.data.split(":")[2])
    full = await get_order_full(db, order_id)
    if not full:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    if actor.role != UserRole.admin and full.manager_id != actor.id:
        await callback.answer("Нет доступа", show_alert=True)
        return

    await update_order_fields(db, order_id, status=OrderStatus.canceled)
    if settings.supergroup_chat_id and full.published_message_id and full.city and full.city.thread_id:
        try:
            await bot.edit_message_text(
                chat_id=settings.supergroup_chat_id,
                message_id=full.published_message_id,
                message_thread_id=full.city.thread_id,
                text="❌ *ОТМЕНЕНО*\n\n" + order_card_text(full),
                reply_markup=None,
            )
        except Exception:
            pass

    if callback.message:
        await callback.message.answer("Заявка отменена.", reply_markup=back_to_menu())
    await callback.answer("Ок")


@router.callback_query(F.data.startswith("pay:client:"))
async def cb_pay_client(callback: CallbackQuery, db: AsyncSession) -> None:
    if not callback.from_user:
        await callback.answer()
        return
    actor = await _require_actor(db, callback.from_user.id)
    if not actor or actor.role not in (UserRole.manager, UserRole.admin) or not actor.is_active:
        await callback.answer("Нет доступа", show_alert=True)
        return

    order_id = int(callback.data.split(":")[2])
    full = await get_order_full(db, order_id)
    if not full:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    if actor.role != UserRole.admin and full.manager_id != actor.id:
        await callback.answer("Нет доступа", show_alert=True)
        return

    await update_order_fields(
        db,
        order_id,
        client_paid=True,
        client_paid_amount=float(full.price_client) if full.price_client is not None else None,
        client_paid_at=datetime.utcnow(),
    )
    if callback.message:
        await callback.message.answer("Отмечено: клиент оплатил ✅")
    await callback.answer("Ок")


@router.callback_query(F.data.startswith("invoice:order:"))
async def cb_invoice_order(callback: CallbackQuery, bot: Bot, db: AsyncSession) -> None:
    if not callback.from_user:
        await callback.answer()
        return
    actor = await _require_actor(db, callback.from_user.id)
    if not actor or actor.role not in (UserRole.manager, UserRole.admin) or not actor.is_active:
        await callback.answer("Нет доступа", show_alert=True)
        return

    order_id = int(callback.data.split(":")[2])
    order = await get_order_full(db, order_id)
    if not order:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    if actor.role != UserRole.admin and order.manager_id != actor.id:
        await callback.answer("Нет доступа", show_alert=True)
        return

    pdf = generate_invoice_pdf(order)
    await bot.send_document(
        chat_id=callback.from_user.id,
        document=BufferedInputFile(pdf.pdf_bytes, filename=pdf.filename),
        caption=f"Счёт по заявке {order.public_id}",
    )
    await callback.answer("Отправлено")


@router.callback_query(F.data.startswith("photo:start:"))
async def cb_photo_start(callback: CallbackQuery, state: FSMContext, db: AsyncSession) -> None:
    if not callback.from_user:
        await callback.answer()
        return
    actor = await _require_actor(db, callback.from_user.id)
    if not actor or actor.role != UserRole.cleaner or not actor.is_active:
        await callback.answer("Нет доступа", show_alert=True)
        return

    order_id = int(callback.data.split(":")[2])
    order = await get_order_full(db, order_id)
    if not order or order.cleaner_id != actor.id:
        await callback.answer("Нет доступа к заявке", show_alert=True)
        return

    await state.clear()
    await state.set_state(PhotoStates.choose_kind)
    await state.update_data(order_id=order_id)
    if callback.message:
        await callback.message.answer("Выбери тип фото:", reply_markup=photo_kind_kb(order_id))
    await callback.answer()


@router.callback_query(F.data.startswith("photo:kind:"))
async def cb_photo_kind(callback: CallbackQuery, state: FSMContext, db: AsyncSession) -> None:
    if not callback.from_user:
        await callback.answer()
        return
    actor = await _require_actor(db, callback.from_user.id)
    if not actor or actor.role != UserRole.cleaner or not actor.is_active:
        await callback.answer("Нет доступа", show_alert=True)
        return

    _, _, order_id_raw, kind_raw = callback.data.split(":", 3)
    order_id = int(order_id_raw)
    kind = PhotoKind(kind_raw)
    order = await get_order_full(db, order_id)
    if not order or order.cleaner_id != actor.id:
        await callback.answer("Нет доступа к заявке", show_alert=True)
        return

    await state.set_state(PhotoStates.upload)
    await state.update_data(order_id=order_id, photo_kind=kind.value)
    if callback.message:
        await callback.message.answer("Отправляй фото (можно несколько). Когда закончишь — нажми «Готово».", reply_markup=photo_done_kb())
    await callback.answer()


@router.message(PhotoStates.upload, F.photo)
async def msg_photo_upload(message: Message, state: FSMContext, db: AsyncSession) -> None:
    if not message.from_user or not message.photo:
        return
    actor = await _require_actor(db, message.from_user.id)
    if not actor or actor.role != UserRole.cleaner or not actor.is_active:
        return

    data = await state.get_data()
    order_id = data.get("order_id")
    kind_raw = data.get("photo_kind")
    if not order_id or not kind_raw:
        await message.answer("Сессия загрузки не найдена. Открой заявку и начни заново.")
        return

    kind = PhotoKind(kind_raw)
    file = message.photo[-1]
    order = await get_order_full(db, int(order_id))
    if not order or order.cleaner_id != actor.id:
        await message.answer("Нет доступа к заявке.")
        return

    db.add(
        OrderPhoto(
            order_id=int(order_id),
            kind=kind,
            telegram_file_id=file.file_id,
            telegram_unique_id=file.file_unique_id or "",
            uploaded_by_user_id=actor.id,
        )
    )
    await db.commit()
    await message.answer("Фото сохранено ✅", reply_markup=photo_done_kb())


@router.callback_query(F.data == "photo:done")
async def cb_photo_done(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message:
        await callback.message.answer("Готово.", reply_markup=back_to_menu())
    await callback.answer()


@router.callback_query()
async def cb_fallback(callback: CallbackQuery) -> None:
    await callback.answer("Неизвестное действие. Обнови меню (/start).", show_alert=True)


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
        await callback.message.answer(f"Меню.\nТвоя роль: *{_role_label(user.role)}*", reply_markup=_menu_for_user(user))
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
    await message.answer(
        f"Готово. Ты добавлен(а) в систему.\nТвоя роль: *{_role_label(user.role)}*",
        reply_markup=_menu_for_user(user),
    )


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
