from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Filter_HH


async def get_user_filters(session: AsyncSession, tg_id: int) -> dict:
    query = select(Filter_HH.filters).where(Filter_HH.tg_id == tg_id)
    result = await session.execute(query)
    filters = result.scalar_one_or_none()
    return filters if filters is not None else {}


async def save_filters(session: AsyncSession, new_filters: dict, tg_id: int) -> dict:
    "полностью обновить фильтры(удаляя всё, что не находится в new_filters)"
    query = select(Filter_HH).where(Filter_HH.tg_id == tg_id)
    result = await session.execute(query)
    filters_db = result.scalar_one_or_none()

    if filters_db:
        filters_db.filters = new_filters
    else:
        filters_db = Filter_HH(tg_id=tg_id, filters=new_filters)
        session.add(filters_db)

    await session.commit()

    return filters_db.filters


async def patch_filters(session: AsyncSession, tg_id: int, update_data: dict) -> dict:
    "Обновить частисно фильтры"
    query = select(Filter_HH).where(Filter_HH.tg_id == tg_id)
    result = await session.execute(query)
    filters_db = result.scalar_one_or_none()

    if not filters_db:
        filters_db = Filter_HH(tg_id=tg_id, filters=update_data)
    else:
        current_filters = dict(filters_db.filters)
        current_filters.update(update_data)
        filters_db.filters = current_filters

    await session.commit()
    return filters_db.filters
