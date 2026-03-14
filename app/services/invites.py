from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Invite, InviteRole, User, UserRole
from app.utils.codes import generate_invite_code
from app.utils.security import hash_code, verify_code


async def create_invite(session: AsyncSession, *, role: InviteRole, created_by: User, ttl_hours: int = 72) -> str:
    code = generate_invite_code()
    invite = Invite(
        role=role,
        code_hash=hash_code(code),
        created_by_user_id=created_by.id,
        expires_at=datetime.utcnow() + timedelta(hours=ttl_hours),
    )
    session.add(invite)
    await session.commit()
    return code


async def consume_invite(session: AsyncSession, *, code: str, telegram_user_id: int, username: str) -> User | None:
    now = datetime.utcnow()
    invites = (await session.scalars(select(Invite).where(Invite.used_at.is_(None)).order_by(Invite.id.desc()))).all()
    for invite in invites:
        if invite.expires_at and invite.expires_at < now:
            continue
        if not verify_code(code, invite.code_hash):
            continue

        role = UserRole.manager if invite.role == InviteRole.manager else UserRole.cleaner
        user = User(telegram_id=telegram_user_id, username=username, role=role, is_active=True)
        session.add(user)
        await session.flush()

        invite.used_at = now
        invite.used_by_user_id = user.id

        await session.commit()
        return user

    return None

