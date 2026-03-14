from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from app.config import settings
from app.db.models import Order
from app.utils.time import format_utc_as_local


@dataclass(frozen=True)
class InvoiceResult:
    filename: str
    pdf_bytes: bytes


def _qr_payload(order: Order) -> str:
    purpose = (settings.payment_purpose_template or "Оплата услуг по заявке {order_public_id}").format(
        order_public_id=order.public_id
    )
    lines = [
        f"Компания: {settings.company_name or '—'}",
        f"ИНН: {settings.company_inn or '—'}",
        f"Банк: {settings.company_bank or '—'}",
        f"Счет: {settings.company_account or '—'}",
        f"БИК: {settings.company_bik or '—'}",
        f"К/с: {settings.company_corr_account or '—'}",
        f"Сумма: {order.price_client or '—'}",
        f"Назначение: {purpose}",
    ]
    return "\n".join(lines)


def generate_invoice_pdf(order: Order) -> InvoiceResult:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, height - 60, "Счет на оплату")

    c.setFont("Helvetica", 11)
    y = height - 100
    c.drawString(40, y, f"Заявка: {order.public_id}")
    y -= 18
    c.drawString(40, y, f"Город: {order.city.name}")
    y -= 18
    c.drawString(40, y, f"Дата/время: {format_utc_as_local(order.scheduled_at)}")
    y -= 18
    c.drawString(40, y, f"Услуга: {order.service_type or '—'}")
    y -= 18
    c.drawString(40, y, f"Сумма: {order.price_client or '—'} ₽")
    y -= 28

    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Реквизиты:")
    y -= 18
    c.setFont("Helvetica", 11)
    c.drawString(40, y, f"Компания: {settings.company_name or '—'}")
    y -= 16
    c.drawString(40, y, f"ИНН: {settings.company_inn or '—'}")
    y -= 16
    c.drawString(40, y, f"Банк: {settings.company_bank or '—'}")
    y -= 16
    c.drawString(40, y, f"Счет: {settings.company_account or '—'}")
    y -= 16
    c.drawString(40, y, f"БИК: {settings.company_bik or '—'}")
    y -= 16
    c.drawString(40, y, f"К/с: {settings.company_corr_account or '—'}")
    y -= 22

    purpose = (settings.payment_purpose_template or "").format(order_public_id=order.public_id)
    c.drawString(40, y, f"Назначение: {purpose or '—'}")

    qr = qrcode.make(_qr_payload(order))
    qr_buf = BytesIO()
    qr.save(qr_buf, format="PNG")
    qr_buf.seek(0)
    img = ImageReader(qr_buf)
    c.drawImage(img, width - 240, height - 320, width=180, height=180, mask="auto")
    c.setFont("Helvetica", 9)
    c.drawString(width - 240, height - 330, "QR для оплаты (текстовый)")

    c.showPage()
    c.save()
    pdf_bytes = buf.getvalue()
    return InvoiceResult(filename=f"invoice_{order.public_id}.pdf", pdf_bytes=pdf_bytes)

