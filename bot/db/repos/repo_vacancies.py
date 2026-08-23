import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import ActionType, User, VacancyAction

logger = structlog.get_logger(__name__)


async def add_vacancy_action(
    session: AsyncSession,
    tg_id: int,
    vacancy: dict,
    action: str,  # "like" или "skip"
    key_skills: list | None = None,
) -> bool:
    """
    Сохраняет лайк или скип в базу данных и обновляет списки навыков.
    Возвращает True в случае успеха, и False если запись уже существует.
    """
    user_stmt = select(User).where(User.tg_id == tg_id)
    user_res = await session.execute(user_stmt)
    db_user = user_res.scalar_one_or_none()

    if not db_user:
        return False

    if action == "like":
        db_action = ActionType.LIKE
    elif action == "view":
        db_action = ActionType.VIEWED
    else:
        db_action = ActionType.SKIP

    try:
        new_action = VacancyAction(
            user_id=db_user.id,
            vacancy_id=str(vacancy.get("id")),
            action=db_action,
            vacancy_title=vacancy.get("name"),
            vacancy_url=vacancy.get("alternate_url"),
        )
        session.add(new_action)

        new_skills = set()

        if key_skills:
            new_skills = set(str(skill).lower() for skill in key_skills if skill)

        if action == "like":
            existing_likes = set(db_user.liked or [])
            db_user.liked = list(existing_likes | new_skills)
        elif action == "skip":
            existing_dislikes = set(db_user.disliked or [])
            db_user.disliked = list(existing_dislikes | new_skills)
        else:
            pass

        await session.commit()
        return True

    except Exception:
        await session.rollback()
        import traceback

        logger.info("!! ОШИБКА !!")

        traceback.print_exc()
        return False


async def get_viewed_vacancy_ids(session: AsyncSession, tg_id: int) -> set[str]:
    """
    Возвращает множество (set) всех ID вакансий, которые пользователь уже лайкнул или скрыл.
    """
    # Сначала находим внутренний ID пользователя по его tg_id
    user_stmt = select(User.id).where(User.tg_id == tg_id)
    user_res = await session.execute(user_stmt)
    db_user_id = user_res.scalar_one_or_none()

    if not db_user_id:
        return set()

    # Выбираем только поле vacancy_id для этого пользователя
    vac_id = select(VacancyAction.vacancy_id).where(VacancyAction.user_id == db_user_id)
    result = await session.execute(vac_id)

    # scalars().all() вернет список строк, превращаем его в set для быстрой фильтрации
    return set(result.scalars().all())


async def get_favorite_vac(session: AsyncSession, tg_id: int) -> list:
    user_tg_id = select(User.id).where(User.tg_id == tg_id)
    user_result = await session.execute(user_tg_id)

    db_user_id = user_result.scalar_one_or_none()

    if not db_user_id:
        return {}

    vac_action = (
        select(VacancyAction)
        .where(VacancyAction.user_id == db_user_id)
        .where(VacancyAction.action == ActionType.LIKE)
    )
    vac_act_res = await session.execute(vac_action)

    favorite_vac = vac_act_res.scalars().all()

    print(favorite_vac)

    return favorite_vac


async def del_fav_vac_from_db(
    session: AsyncSession, tg_id: int, vacancy_id: str
) -> bool:

    user_tg_id = select(User.id).where(User.tg_id == tg_id)
    user_result = await session.execute(user_tg_id)

    db_user_id = user_result.scalar_one_or_none()

    if not db_user_id:
        return 0

    delete_vac = delete(VacancyAction).where(
        VacancyAction.user_id == db_user_id, VacancyAction.vacancy_id == str(vacancy_id)
    )
    await session.execute(delete_vac)
    await session.commit()


async def get_last_vacancy_check(session: AsyncSession, tg_id: int):
    user_tg_id = select(User.id).where(User.tg_id == tg_id)
    user_result = await session.execute(user_tg_id)

    db_user_id = user_result.scalar_one_or_none()
    if not db_user_id:
        return 0

    last_vacancy_check_select = select(User.last_vacancy_check).where(
        User.tg_id == tg_id
    )
    last_vacancy_check_res = await session.execute(last_vacancy_check_select)

    last_vacancy_check = last_vacancy_check_res.scalar_one()

    print(last_vacancy_check)

    return last_vacancy_check
