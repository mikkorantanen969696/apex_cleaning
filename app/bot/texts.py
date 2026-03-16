from __future__ import annotations

from app.db.models import Order
from app.utils.time import format_utc_as_local


def order_card_text(order: Order) -> str:
    when = format_utc_as_local(order.scheduled_at)
    price = f"{order.price_client:.2f} ₽" if order.price_client is not None else "—"
    area = f"{order.area_sqm:.0f} м²" if getattr(order, "area_sqm", None) is not None else "—"
    rooms = str(order.rooms_count) if getattr(order, "rooms_count", None) is not None else "—"
    detergents = "есть" if getattr(order, "detergents_on_site", True) else "нет"
    parts = [
        f"🧾 *Заявка {order.public_id}*",
        f"🏙 Город: *{order.city.name}*",
        f"🧼 Услуга: *{order.service_type or '—'}*",
        f"🧽 Тип уборки: *{getattr(order, 'cleaning_type', '') or '—'}*",
        f"🕒 Когда: *{when}*",
        f"📍 Адрес: *{order.address or '—'}*",
        f"📐 Площадь: *{area}* | Комнат: *{rooms}*",
        f"🧴 Мойка/химия на месте: *{detergents}*",
        f"💳 Цена: *{price}*",
    ]
    equipment = (getattr(order, "equipment_required", "") or "").strip()
    if equipment:
        parts.append(f"🧰 Оборудование: {equipment}")
    scope = (getattr(order, "work_scope", "") or "").strip()
    if scope:
        parts.append(f"📋 Объём работ: {scope}")
    if order.comment:
        parts.append(f"💬 Комментарий: {order.comment}")
    parts.append("")
    parts.append("Нажми кнопку ниже, чтобы взять заказ 👇")
    return "\n".join(parts)


def order_private_details(order: Order) -> str:
    when = format_utc_as_local(order.scheduled_at)
    price = f"{order.price_client:.2f} ₽" if order.price_client is not None else "—"
    area = f"{order.area_sqm:.0f} м²" if getattr(order, "area_sqm", None) is not None else "—"
    rooms = str(order.rooms_count) if getattr(order, "rooms_count", None) is not None else "—"
    detergents = "есть" if getattr(order, "detergents_on_site", True) else "нет"
    parts = [
        f"🧾 *{order.public_id}*",
        f"🏙 Город: *{order.city.name}*",
        f"🧼 Услуга: *{order.service_type or '—'}*",
        f"🧽 Тип уборки: *{getattr(order, 'cleaning_type', '') or '—'}*",
        f"🕒 Когда: *{when}*",
        f"📍 Адрес: *{order.address or '—'}*",
        f"📐 Площадь: *{area}* | Комнат: *{rooms}*",
        f"🧴 Мойка/химия на месте: *{detergents}*",
        f"👤 Клиент: *{order.client_name or '—'}*",
        f"📞 Телефон: `{order.client_phone or '—'}`",
        f"💳 Цена: *{price}*",
    ]
    equipment = (getattr(order, "equipment_required", "") or "").strip()
    if equipment:
        parts.append(f"🧰 Оборудование: {equipment}")
    scope = (getattr(order, "work_scope", "") or "").strip()
    if scope:
        parts.append(f"📋 Объём работ: {scope}")
    if order.comment:
        parts.append(f"💬 Комментарий: {order.comment}")
    return "\n".join(parts)
