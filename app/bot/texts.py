from __future__ import annotations

from app.db.models import Order, OrderStatus
from app.utils.time import format_utc_as_local


def _fmt_bool(value: bool | None) -> str:
    if value is None:
        return "неизвестно"
    return "да" if value else "нет"


def _fmt_status(status: OrderStatus) -> str:
    mapping = {
        OrderStatus.draft: "черновик",
        OrderStatus.published: "опубликовано",
        OrderStatus.assigned: "назначено",
        OrderStatus.in_progress: "в работе",
        OrderStatus.done: "выполнено",
        OrderStatus.canceled: "отменено",
    }
    return mapping.get(status, status.value)


def order_card_text(order: Order) -> str:
    when = format_utc_as_local(order.scheduled_at)
    price = f"{float(order.price_client):.2f} ₽" if order.price_client is not None else "—"
    area = f"{float(order.area_sqm):.0f} м²" if order.area_sqm is not None else "—"
    rooms = str(order.rooms_count) if order.rooms_count is not None else "—"
    baths = str(order.bathrooms_count) if order.bathrooms_count is not None else "—"

    parts = [
        f"🧾 *Заявка {order.public_id}*",
        f"🏷 Статус: *{_fmt_status(order.status)}*",
        f"🏙 Город: *{order.city.name}*",
        f"🧽 Тип уборки: *{order.cleaning_type or '—'}*",
        f"🧼 Услуга: *{order.service_type or '—'}*",
        f"🕒 Когда: *{when}*",
        f"📍 Адрес: *{order.address or '—'}*",
        f"📐 Площадь: *{area}* | Комнат: *{rooms}* | Санузлов: *{baths}*",
        f"🧴 Моющие средства на месте: *{_fmt_bool(order.detergents_on_site)}*",
        f"💳 Цена: *{price}*",
    ]

    if order.equipment_required.strip():
        parts.append(f"🧰 Оборудование/инвентарь: {order.equipment_required.strip()}")
    if order.work_scope.strip():
        parts.append(f"📋 Объем работ: {order.work_scope.strip()}")
    if order.comment.strip():
        parts.append(f"💬 Комментарий: {order.comment.strip()}")

    parts.append("")
    if order.status == OrderStatus.published and order.cleaner_id is None:
        parts.append("Нажми кнопку ниже, чтобы взять заказ 👇")
    else:
        parts.append(f"Статус: *{_fmt_status(order.status)}*")
    return "\n".join(parts)


def order_private_details(order: Order) -> str:
    when = format_utc_as_local(order.scheduled_at)
    price = f"{float(order.price_client):.2f} ₽" if order.price_client is not None else "—"
    area = f"{float(order.area_sqm):.0f} м²" if order.area_sqm is not None else "—"
    rooms = str(order.rooms_count) if order.rooms_count is not None else "—"
    baths = str(order.bathrooms_count) if order.bathrooms_count is not None else "—"

    parts = [
        f"🧾 *{order.public_id}*",
        f"🏷 Статус: *{_fmt_status(order.status)}*",
        f"🏙 Город: *{order.city.name}*",
        f"🧽 Тип уборки: *{order.cleaning_type or '—'}*",
        f"🧼 Услуга: *{order.service_type or '—'}*",
        f"🕒 Когда: *{when}*",
        f"📍 Адрес: *{order.address or '—'}*",
        f"📐 Площадь: *{area}* | Комнат: *{rooms}* | Санузлов: *{baths}*",
        f"🧴 Моющие средства на месте: *{_fmt_bool(order.detergents_on_site)}*",
        f"🧹 Пылесос на месте: *{_fmt_bool(order.vacuum_on_site)}*",
        f"🪜 Стремянка на месте: *{_fmt_bool(order.ladder_on_site)}*",
        f"👤 Клиент: *{order.client_name or '—'}*",
        f"📞 Телефон: `{order.client_phone or '—'}`",
        f"☎️ Связь: *{order.client_contact_method or '—'}*",
        f"💳 Цена: *{price}*",
    ]

    if order.equipment_required.strip():
        parts.append(f"🧰 Оборудование/инвентарь: {order.equipment_required.strip()}")
    if order.work_scope.strip():
        parts.append(f"📋 Объем работ: {order.work_scope.strip()}")
    if order.access_notes.strip():
        parts.append(f"🧭 Доступ/парковка/этаж: {order.access_notes.strip()}")
    if order.comment.strip():
        parts.append(f"💬 Комментарий: {order.comment.strip()}")
    return "\n".join(parts)
