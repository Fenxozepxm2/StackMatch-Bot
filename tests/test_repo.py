from datetime import UTC, datetime

import pytest

from bot.db.repos.repo_filters import get_user_filters, save_filters
from bot.db.repos.repo_user import get_user, save_user
from bot.db.repos.repo_vacancies import add_vacancy_action


@pytest.mark.asyncio
async def test_save_user(db_session):
    user = await save_user(
        session=db_session,
        tg_id=123456,
        username="testuser",
        last_seen_in_bot=datetime.now(UTC),
        created_at=datetime.now(UTC),
        name="Test",
    )
    assert user.id is not None
    assert user.tg_id == 123456


@pytest.mark.asyncio
async def test_get_user_not_found(db_session):
    with pytest.raises(ValueError):
        await get_user(db_session, tg_id=999)


@pytest.mark.asyncio
async def test_save_filters(db_session):

    user = await save_user(
        db_session,
        tg_id=123,
        username="u",
        last_seen_in_bot=datetime.now(UTC),
        created_at=datetime.now(UTC),
        name="N",
    )

    filters_dict = {"city": "Москва", "salary_from": 70000}
    saved = await save_filters(db_session, filters_dict, tg_id=123)
    assert saved["city"] == "Москва"
    # Проверка, что фильтр сохранился в БД
    loaded = await get_user_filters(db_session, tg_id=123)
    assert loaded.get("city") == "Москва"


@pytest.mark.asyncio
async def test_add_vacancy_action(db_session):

    user = await save_user(
        db_session,
        tg_id=123,
        username="u",
        last_seen_in_bot=datetime.now(UTC),
        created_at=datetime.now(UTC),
        name="N",
    )

    vac_data = {"id": "1", "name": "Python dev", "alternate_url": "https://hh.ru/1"}
    skills = ["python", "django", "postgresql"]

    result = await add_vacancy_action(
        db_session, tg_id=123, vacancy=vac_data, action="like", key_skills=skills
    )
    assert result is True

    # Проверяем, что навыки добавились в user.liked
    user_updated = await get_user(db_session, tg_id=123)
    assert "python" in user_updated.liked
    assert "django" in user_updated.liked


@pytest.mark.asyncio
async def test_add_vacancy_action_with_skills(db_session):
    user = await save_user(
        db_session,
        tg_id=123,
        username="u",
        last_seen_in_bot=datetime.now(UTC),
        created_at=datetime.now(UTC),
        name="N",
    )

    vac_data = {"id": "1", "name": "Python dev", "alternate_url": "https://hh.ru/1"}
    skills = ["python", "django", "postgresql"]

    result = await add_vacancy_action(
        db_session, tg_id=123, vacancy=vac_data, action="like", key_skills=skills
    )
    assert result is True

    # Проверяем, что навыки добавились в user.liked
    user_updated = await get_user(db_session, tg_id=123)
    assert "python" in user_updated.liked
    assert "django" in user_updated.liked
