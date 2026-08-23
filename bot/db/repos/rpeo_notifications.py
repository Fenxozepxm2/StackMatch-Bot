from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import User, User_notification


async def get_top5_vaca_in_notification(session: AsyncSession, tg_id: int) -> dict:
    user_stmt = select(User).where(User.tg_id == tg_id)
    user_res = await session.execute(user_stmt)
    db_user = user_res.scalar_one_or_none()

    if not db_user:
        return False

    top5_vacs_query = await session.execute(
        select(User_notification.vacancy_data).where(User_notification.tg_id == tg_id)
    )
    top_5_vacs = top5_vacs_query.scalars().all()

    # мб тут изменять флаг просмотра вакансии, что бы лишний раз не обращаться к БД, я ещё подумаю над этим

    return top_5_vacs


async def add_top5_vaca_in_notification(
    session: AsyncSession,
    tg_id: int,
    vaca: dict,
):

    try:
        vac_id = str(vaca.get("id"))

        # ищем нет ли такого же уведомления для этого юзера
        query = select(User_notification).where(
            User_notification.tg_id == tg_id, User_notification.vacancy_id == vac_id
        )
        result = await session.execute(query)
        already_exists = result.scalar_one_or_none()

        if not already_exists:
            new_viewed_vacancy = User_notification(
                tg_id=tg_id,
                vacancy_id=str(vaca.get("id")),
                vacancy_data=vaca,
                sent_at=datetime.now(tz="UTC"),
            )
            session.add(new_viewed_vacancy)
            await session.commit()
        else:
            print(f"Вакансия {vac_id} уже есть в уведомлениях у {tg_id}, пропускаем.")

    except Exception:
        await session.rollback()
        import traceback

        traceback.print_exc()


async def del_top5_vaca_in_notification(
    session: AsyncSession,
    tg_id: int,
) -> bool:

    user_stmt = select(User).where(User.tg_id == tg_id)
    user_res = await session.execute(user_stmt)
    db_user = user_res.scalar_one_or_none()

    if not db_user:
        return False

    try:
        del_vacs = delete(User_notification).where(User_notification.tg_id == tg_id)
        await session.execute(del_vacs)

        await session.commit()

    except Exception:
        await session.rollback()
        import traceback

        traceback.print_exc()
        return False
    return True
