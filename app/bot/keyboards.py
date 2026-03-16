from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.db.models import PhotoKind


def main_menu_admin(role_label: str | None = None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if role_label:
        kb.button(text=f"👤 {role_label}", callback_data="noop")
    kb.button(text="👥 Менеджеры", callback_data="admin:managers")
    kb.button(text="🧹 Клинеры", callback_data="admin:cleaners")
    kb.button(text="🏙 Города/Темы", callback_data="admin:cities")
    kb.button(text="🧾 Заявки", callback_data="admin:orders")
    kb.button(text="📊 Экспорт", callback_data="admin:export")
    kb.adjust(1, 2, 2, 1)
    return kb.as_markup()


def main_menu_manager(role_label: str | None = None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if role_label:
        kb.button(text=f"👤 {role_label}", callback_data="noop")
    kb.button(text="➕ Создать заявку", callback_data="mgr:create_order")
    kb.button(text="🧾 Мои заявки", callback_data="mgr:my_orders")
    kb.button(text="📄 Счет (PDF+QR)", callback_data="mgr:invoice")
    kb.button(text="📊 Мой экспорт", callback_data="mgr:export")
    kb.adjust(1, 1, 1, 1, 1)
    return kb.as_markup()


def main_menu_cleaner(role_label: str | None = None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if role_label:
        kb.button(text=f"👤 {role_label}", callback_data="noop")
    kb.button(text="📋 Доступные заявки", callback_data="cln:available")
    kb.button(text="🧾 Мои заказы", callback_data="cln:my_orders")
    kb.adjust(1, 1, 1)
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
    kb.button(text="⬅️ Назад", callback_data=f"order:open:{order_id}")
    kb.adjust(1, 1, 1)
    return kb.as_markup()


def order_actions_kb(order_id: int, *, is_manager: bool, is_cleaner: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if is_cleaner:
        kb.button(text="📷 Загрузить фото", callback_data=f"photo:start:{order_id}")
        kb.button(text="🚧 В работе", callback_data=f"order:status:{order_id}:in_progress")
        kb.button(text="✅ Выполнено", callback_data=f"order:status:{order_id}:done")
    if is_manager:
        kb.button(text="💰 Клиент оплатил", callback_data=f"pay:client:{order_id}")
        kb.button(text="📄 Счет (PDF+QR)", callback_data=f"invoice:order:{order_id}")
        kb.button(text="❌ Отменить заявку", callback_data=f"order:cancel:{order_id}")
    kb.button(text="⬅️ В меню", callback_data="menu")
    kb.adjust(1, 1, 1)
    return kb.as_markup()


def yes_no_kb(yes_cb: str, no_cb: str, *, back_cb: str | None = None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Да", callback_data=yes_cb)
    kb.button(text="❌ Нет", callback_data=no_cb)
    if back_cb:
        kb.button(text="⬅️ Назад", callback_data=back_cb)
    kb.adjust(2, 1)
    return kb.as_markup()


def tri_kb(yes_cb: str, no_cb: str, unknown_cb: str, *, back_cb: str | None = None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Да", callback_data=yes_cb)
    kb.button(text="❌ Нет", callback_data=no_cb)
    kb.button(text="❔ Не знаю", callback_data=unknown_cb)
    if back_cb:
        kb.button(text="⬅️ Назад", callback_data=back_cb)
    kb.adjust(3, 1)
    return kb.as_markup()


def cleaning_type_kb() -> InlineKeyboardMarkup:
    options = [
        ("Поддерживающая", "Поддерживающая"),
        ("Генеральная", "Генеральная"),
        ("После ремонта", "После ремонта"),
        ("Окна", "Окна"),
        ("Другое", "Другое"),
    ]
    kb = InlineKeyboardBuilder()
    for label, value in options:
        kb.button(text=label, callback_data=f"mgr:cleaning_type:{value}")
    kb.button(text="⬅️ Назад", callback_data="mgr:back:service_type")
    kb.adjust(2, 2, 1, 1)
    return kb.as_markup()


def contact_method_kb() -> InlineKeyboardMarkup:
    options = [
        ("Звонок", "call"),
        ("WhatsApp", "whatsapp"),
        ("Telegram", "telegram"),
        ("Любой", "any"),
    ]
    kb = InlineKeyboardBuilder()
    for label, value in options:
        kb.button(text=label, callback_data=f"mgr:contact_method:{value}")
    kb.button(text="⬅️ Назад", callback_data="mgr:back:client_phone")
    kb.adjust(2, 2, 1)
    return kb.as_markup()


def admin_invite_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Код для менеджера", callback_data="admin:invite:manager")
    kb.button(text="➕ Код для клинера", callback_data="admin:invite:cleaner")
    kb.button(text="⬅️ В меню", callback_data="menu")
    kb.adjust(1, 1, 1)
    return kb.as_markup()


def photo_done_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✅ Готово", callback_data="photo:done")], [InlineKeyboardButton(text="⬅️ В меню", callback_data="menu")]]
    )
