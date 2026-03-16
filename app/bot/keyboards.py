from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.db.models import PhotoKind


def main_menu_admin() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="👥 Менеджеры", callback_data="admin:managers")
    kb.button(text="🧹 Клинеры", callback_data="admin:cleaners")
    kb.button(text="🏙 Города/Темы", callback_data="admin:cities")
    kb.button(text="🧾 Заявки", callback_data="admin:orders")
    kb.button(text="📊 Экспорт", callback_data="admin:export")
    kb.adjust(2, 2, 1)
    return kb.as_markup()


def main_menu_manager() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Создать заявку", callback_data="mgr:create_order")
    kb.button(text="🧾 Мои заявки", callback_data="mgr:my_orders")
    kb.button(text="📄 Счет (PDF+QR)", callback_data="mgr:invoice")
    kb.button(text="📊 Моя статистика", callback_data="mgr:export")
    kb.adjust(1, 1, 1, 1)
    return kb.as_markup()


def main_menu_cleaner() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 Доступные заявки", callback_data="cln:available")
    kb.button(text="🧾 Мои заказы", callback_data="cln:my_orders")
    kb.adjust(1, 1)
    return kb.as_markup()


def back_to_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ В меню", callback_data="menu")]])


def confirm_create_order() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Опубликовать", callback_data="mgr:publish_order")
    kb.button(text="❌ Отмена", callback_data="mgr:cancel_create")
    kb.adjust(1, 1)
    return kb.as_markup()


def order_take_button(order_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Взять заказ", callback_data=f"order:take:{order_id}")
    return kb.as_markup()


def order_taken_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⛔ Занято", callback_data="noop")]])


def photo_kind_kb(order_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📷 Фото ДО", callback_data=f"photo:kind:{order_id}:{PhotoKind.before.value}")
    kb.button(text="📷 Фото ПОСЛЕ", callback_data=f"photo:kind:{order_id}:{PhotoKind.after.value}")
    kb.button(text="⬅️ Назад", callback_data=f"order:actions:{order_id}")
    kb.adjust(1, 1, 1)
    return kb.as_markup()


def order_actions_kb(order_id: int, is_manager: bool, is_cleaner: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if is_cleaner:
        kb.button(text="📷 Загрузить фото", callback_data=f"photo:start:{order_id}")
    if is_manager:
        kb.button(text="💰 Отметить оплату клиента", callback_data=f"pay:client:{order_id}")
        kb.button(text="📄 Счет (PDF+QR)", callback_data=f"invoice:order:{order_id}")
    if is_cleaner:
        kb.button(text="🚧 В работе", callback_data=f"order:status:{order_id}:in_progress")
        kb.button(text="✅ Выполнено", callback_data=f"order:status:{order_id}:done")
    kb.button(text="⬅️ В меню", callback_data="menu")
    kb.adjust(1, 1, 1)
    return kb.as_markup()
