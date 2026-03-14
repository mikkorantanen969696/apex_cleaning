from __future__ import annotations

from app.db.models import Order
from app.utils.time import format_utc_as_local


def order_card_text(order: Order) -> str:
    when = format_utc_as_local(order.scheduled_at)
    price = f"{order.price_client:.2f} ₽" if order.price_client is not None else "—"
    parts = [
        f"🧾 *Заявка {order.public_id}*",
        f"🏙 Город: *{order.city.name}*",
        f"🧼 Услуга: *{order.service_type or '—'}*",
        f"🕒 Когда: *{when}*",
        f"📍 Адрес: *{order.address or '—'}*",
        f"💳 Цена: *{price}*",
    ]
    if order.comment:
        parts.append(f"💬 Комментарий: {order.comment}")
    parts.append("")
    parts.append("Нажми кнопку ниже, чтобы взять заказ 👇")
    return "\n".join(parts)


def order_private_details(order: Order) -> str:
    when = format_utc_as_local(order.scheduled_at)
    price = f"{order.price_client:.2f} ₽" if order.price_client is not None else "—"
    parts = [
        f"🧾 *{order.public_id}*",
        f"🏙 Город: *{order.city.name}*",
        f"🧼 Услуга: *{order.service_type or '—'}*",
        f"🕒 Когда: *{when}*",
        f"📍 Адрес: *{order.address or '—'}*",
        f"👤 Клиент: *{order.client_name or '—'}*",
        f"📞 Телефон: `{order.client_phone or '—'}`",
        f"💳 Цена: *{price}*",
    ]
    if order.comment:
        parts.append(f"💬 Комментарий: {order.comment}")
    return "\n".join(parts)

