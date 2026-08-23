from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import User


async def save_user(
    session: AsyncSession,
    tg_id: int,
    username: str,
    last_seen_in_bot: datetime,
    created_at: datetime,
    name: str,
) -> User:
    "Запись нового юзера в БД"

    query = select(User).where(User.tg_id == tg_id)
    result = await session.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            tg_id=tg_id,
            username=username,
            last_seen_in_bot=last_seen_in_bot,
            created_at=created_at,
            name=name,
        )
        session.add(user)
        await session.commit()
        return user
    else:
        return user


async def get_user(
    session: AsyncSession,
    tg_id: int,
    username: str | None = None,
) -> User:
    "Получение юзера из БД"
    query = await session.execute(select(User).where(User.tg_id == tg_id))
    user = query.scalar_one_or_none()
    if not user:
        raise ValueError()

    return user


async def get_users(session: AsyncSession) -> User:
    query = await session.execute(select(User))
    users = query.scalars().all()
    if not users:
        raise ValueError()

    return users
