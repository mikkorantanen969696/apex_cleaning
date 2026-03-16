from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import City, Order, OrderStatus, User, UserRole


async def next_public_id(session: AsyncSession) -> str:
    count = await session.scalar(select(func.count(Order.id)))
    num = int(count or 0) + 1
    return f"APEX-{num:06d}"


async def list_cities(session: AsyncSession) -> list[City]:
    return (await session.scalars(select(City).where(City.is_active.is_(True)).order_by(City.name.asc()))).all()


async def get_city(session: AsyncSession, city_id: int) -> City | None:
    return await session.scalar(select(City).where(City.id == city_id, City.is_active.is_(True)))


async def create_order_draft(session: AsyncSession, *, manager: User, city: City) -> Order:
    public_id = await next_public_id(session)
    order = Order(
        public_id=public_id,
        city_id=city.id,
        manager_id=manager.id,
        status=OrderStatus.draft,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    session.add(order)
    await session.commit()
    return order


async def update_order_fields(session: AsyncSession, order_id: int, **fields) -> Order | None:
    order = await session.scalar(select(Order).where(Order.id == order_id))
    if not order:
        return None
    for k, v in fields.items():
        setattr(order, k, v)
    order.updated_at = datetime.utcnow()
    await session.commit()
    return order


async def publish_order(session: AsyncSession, order_id: int, published_message_id: int) -> Order | None:
    return await update_order_fields(
        session,
        order_id,
        status=OrderStatus.published,
        published_message_id=published_message_id,
    )


async def take_order_atomic(session: AsyncSession, *, order_id: int, cleaner: User) -> Order | None:
    if cleaner.role != UserRole.cleaner:
        return None

    stmt = (
        update(Order)
        .where(and_(Order.id == order_id, Order.status == OrderStatus.published, Order.cleaner_id.is_(None)))
        .values(cleaner_id=cleaner.id, status=OrderStatus.assigned, updated_at=datetime.utcnow())
        .returning(Order)
    )
    result = await session.execute(stmt)
    row = result.first()
    if not row:
        await session.rollback()
        return None
    await session.commit()
    return row[0]


async def get_order(session: AsyncSession, order_id: int) -> Order | None:
    return await session.scalar(select(Order).where(Order.id == order_id))


async def get_order_full(session: AsyncSession, order_id: int) -> Order | None:
    stmt = (
        select(Order)
        .where(Order.id == order_id)
        .options(selectinload(Order.city), selectinload(Order.manager), selectinload(Order.cleaner), selectinload(Order.photos))
    )
    return await session.scalar(stmt)


async def list_recent_orders(session: AsyncSession, limit: int = 20) -> list[Order]:
    stmt = select(Order).order_by(Order.id.desc()).limit(limit).options(selectinload(Order.city))
    return (await session.scalars(stmt)).all()


async def list_manager_orders(session: AsyncSession, manager_user_id: int, limit: int = 20) -> list[Order]:
    return (
        (await session.scalars(select(Order).where(Order.manager_id == manager_user_id).order_by(Order.id.desc()).limit(limit)))
        .all()
    )


async def list_cleaner_orders(session: AsyncSession, cleaner_user_id: int, limit: int = 20) -> list[Order]:
    return (
        (await session.scalars(select(Order).where(Order.cleaner_id == cleaner_user_id).order_by(Order.id.desc()).limit(limit)))
        .all()
    )


async def list_available_orders(session: AsyncSession, limit: int = 20) -> list[Order]:
    return (
        (
            await session.scalars(
                select(Order)
                .where(Order.status == OrderStatus.published, Order.cleaner_id.is_(None))
                .order_by(Order.id.desc())
                .limit(limit)
            )
        )
        .all()
    )


def safe_decimal(value: str) -> Decimal | None:
    value = value.strip().replace(",", ".")
    if not value:
        return None
    try:
        return Decimal(value)
    except Exception:
        return None
