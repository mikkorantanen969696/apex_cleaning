from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class UserRole(str, enum.Enum):
    admin = "admin"
    manager = "manager"
    cleaner = "cleaner"


class InviteRole(str, enum.Enum):
    manager = "manager"
    cleaner = "cleaner"


class OrderStatus(str, enum.Enum):
    draft = "draft"
    published = "published"
    assigned = "assigned"
    in_progress = "in_progress"
    done = "done"
    canceled = "canceled"


class PhotoKind(str, enum.Enum):
    before = "before"
    after = "after"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str] = mapped_column(String(64), default="", server_default="")
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    manager_orders: Mapped[list["Order"]] = relationship(back_populates="manager", foreign_keys="Order.manager_id")
    cleaner_orders: Mapped[list["Order"]] = relationship(back_populates="cleaner", foreign_keys="Order.cleaner_id")


class Invite(Base):
    __tablename__ = "invites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role: Mapped[InviteRole] = mapped_column(Enum(InviteRole), index=True)
    code_hash: Mapped[str] = mapped_column(String(128))
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    used_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)


class City(Base):
    __tablename__ = "cities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    thread_id: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")


class CleanerCity(Base):
    __tablename__ = "cleaner_cities"
    __table_args__ = (UniqueConstraint("cleaner_user_id", "city_id", name="uq_cleaner_city"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cleaner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"))


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)

    city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"))
    manager_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    cleaner_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)

    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus), index=True)

    service_type: Mapped[str] = mapped_column(String(64), default="", server_default="")
    cleaning_type: Mapped[str] = mapped_column(String(64), default="", server_default="")
    address: Mapped[str] = mapped_column(String(255), default="", server_default="")
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    client_name: Mapped[str] = mapped_column(String(64), default="", server_default="")
    client_phone: Mapped[str] = mapped_column(String(32), default="", server_default="")

    area_sqm: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    rooms_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    detergents_on_site: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    equipment_required: Mapped[str] = mapped_column(Text, default="", server_default="")
    work_scope: Mapped[str] = mapped_column(Text, default="", server_default="")

    price_client: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    comment: Mapped[str] = mapped_column(Text, default="", server_default="")

    published_message_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    client_paid: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    client_paid_amount: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    client_paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    cleaner_paid: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    cleaner_paid_amount: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    cleaner_paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    city: Mapped["City"] = relationship()
    manager: Mapped["User"] = relationship(back_populates="manager_orders", foreign_keys=[manager_id])
    cleaner: Mapped[Optional["User"]] = relationship(back_populates="cleaner_orders", foreign_keys=[cleaner_id])
    photos: Mapped[list["OrderPhoto"]] = relationship(back_populates="order")


class OrderPhoto(Base):
    __tablename__ = "order_photos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    kind: Mapped[PhotoKind] = mapped_column(Enum(PhotoKind), index=True)
    telegram_file_id: Mapped[str] = mapped_column(String(256))
    telegram_unique_id: Mapped[str] = mapped_column(String(256), default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    uploaded_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    order: Mapped["Order"] = relationship(back_populates="photos")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    payload_json: Mapped[str] = mapped_column(Text, default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
