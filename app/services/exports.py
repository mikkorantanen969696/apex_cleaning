from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from io import StringIO

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Order
from app.utils.time import format_utc_as_local


@dataclass(frozen=True)
class ExportFile:
    filename: str
    content: bytes


async def export_orders_csv(session: AsyncSession, *, manager_user_id: int | None = None, limit: int = 5000) -> ExportFile:
    stmt = select(Order).order_by(Order.id.desc()).limit(limit)
    if manager_user_id is not None:
        stmt = stmt.where(Order.manager_id == manager_user_id)
    orders = (await session.scalars(stmt)).all()

    out = StringIO()
    writer = csv.writer(out)
    writer.writerow(
        [
            "public_id",
            "status",
            "city_id",
            "manager_id",
            "cleaner_id",
            "cleaning_type",
            "service_type",
            "address",
            "scheduled_at_local",
            "area_sqm",
            "rooms_count",
            "bathrooms_count",
            "detergents_on_site",
            "vacuum_on_site",
            "ladder_on_site",
            "equipment_required",
            "work_scope",
            "access_notes",
            "client_name",
            "client_phone",
            "client_contact_method",
            "price_client",
            "client_paid",
            "created_at",
        ]
    )
    for o in orders:
        writer.writerow(
            [
                o.public_id,
                o.status.value,
                o.city_id,
                o.manager_id,
                o.cleaner_id or "",
                o.cleaning_type or "",
                o.service_type or "",
                o.address or "",
                format_utc_as_local(o.scheduled_at),
                str(o.area_sqm) if o.area_sqm is not None else "",
                o.rooms_count or "",
                o.bathrooms_count or "",
                int(bool(o.detergents_on_site)),
                "" if o.vacuum_on_site is None else int(bool(o.vacuum_on_site)),
                "" if o.ladder_on_site is None else int(bool(o.ladder_on_site)),
                o.equipment_required or "",
                o.work_scope or "",
                o.access_notes or "",
                o.client_name or "",
                o.client_phone or "",
                o.client_contact_method or "",
                str(o.price_client) if o.price_client is not None else "",
                int(bool(o.client_paid)),
                o.created_at.isoformat() if o.created_at else "",
            ]
        )

    return ExportFile(filename="orders_export.csv", content=out.getvalue().encode("utf-8-sig"))


async def export_orders_json(session: AsyncSession, *, manager_user_id: int | None = None, limit: int = 5000) -> ExportFile:
    stmt = select(Order).order_by(Order.id.desc()).limit(limit)
    if manager_user_id is not None:
        stmt = stmt.where(Order.manager_id == manager_user_id)
    orders = (await session.scalars(stmt)).all()

    payload = []
    for o in orders:
        payload.append(
            {
                "public_id": o.public_id,
                "status": o.status.value,
                "city_id": o.city_id,
                "manager_id": o.manager_id,
                "cleaner_id": o.cleaner_id,
                "cleaning_type": o.cleaning_type,
                "service_type": o.service_type,
                "address": o.address,
                "scheduled_at": o.scheduled_at.isoformat() if o.scheduled_at else None,
                "area_sqm": float(o.area_sqm) if o.area_sqm is not None else None,
                "rooms_count": o.rooms_count,
                "bathrooms_count": o.bathrooms_count,
                "detergents_on_site": bool(o.detergents_on_site),
                "vacuum_on_site": o.vacuum_on_site,
                "ladder_on_site": o.ladder_on_site,
                "equipment_required": o.equipment_required,
                "work_scope": o.work_scope,
                "access_notes": o.access_notes,
                "client_name": o.client_name,
                "client_phone": o.client_phone,
                "client_contact_method": o.client_contact_method,
                "price_client": float(o.price_client) if o.price_client is not None else None,
                "client_paid": bool(o.client_paid),
                "created_at": o.created_at.isoformat() if o.created_at else None,
            }
        )

    return ExportFile(filename="orders_export.json", content=json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))

