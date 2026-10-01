from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import User


async def save_user(
    session: AsyncSession,
    tg_id: int,
    username: str | None = None,
    name: str | None = None,
) -> User:
    "Запись нового юзера в БД"
    from bot.handlers.start_bot import utc_now


    query = select(User).where(User.tg_id == tg_id)
    result = await session.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            tg_id=tg_id,
            username=username,
            last_seen_in_bot=utc_now(),
            created_at=utc_now(),
            name=name,
        )
        session.add(user)
    else:
        user.last_seen_in_bot = utc_now()


    await session.commit()

    await session.refresh(user) 
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


async def get_all_user_ids(session: AsyncSession) -> list[int]:
    """Возвращает чистый список telegram_id всех пользователей базы."""
    result = await session.execute(select(User.tg_id))
    return list(result.scalars().all())