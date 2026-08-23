from datetime import UTC, datetime

import requests
import structlog
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import load_config
from bot.db.repos.repo_user import save_user
from bot.handlers.filters import show_filters
from bot.handlers.find_vacancies import finder
from bot.handlers.vac_history import show_all_history_messages
from bot.services.city_mapper import CityMapper
from bot.services.main_menu import send_main_menu
from bot.services.send_daily_vac import check_vacancies

logger = structlog.get_logger(__name__)


config = load_config()


router = Router(name="start")


def utc_now() -> str:
    """Возвращает строку с текущим UTC-временем"""
    now = datetime.now(UTC)
    return now.replace(microsecond=0)


def build_city_id_map():
    url = "https://api.hh.ru/areas"
    response = requests.get(url)
    data = response.json()
    city_map = {}

    def recursive_search(areas):
        for area in areas:
            # Если у зоны есть вложенные области, значит это регион, а не город
            if area.get("areas"):
                recursive_search(area["areas"])
            else:
                # Это город, добавляем его в словарь
                city_map[area["name"].lower()] = area["id"]

    recursive_search(data)
    return city_map


@router.message(CommandStart())
async def start(message: Message, session: AsyncSession) -> None:
    logger.info(
        "user_start_bot",
        user_id=message.from_user.id,
        username=message.from_user.username,
        command="/start",
    )

    await send_main_menu(message, session, edit=False)

    print(utc_now)

    user = await save_user(
        session=session,
        tg_id=message.from_user.id,
        username=message.from_user.username,
        last_seen_in_bot=utc_now(),
        created_at=utc_now(),
        name=message.from_user.first_name,
    )

    await CityMapper.load_cities()


@router.message(Command("test"))
async def for_tests(message: Message, session: AsyncSession):
    # from bot.services.to_hhApi import HHAPI
    # # await HHAPI.full_vacanci_id(vac_id=134916211, access_token=config.access_token.access_token, session= AsyncSession)
    # user = await get_user(session, message.from_user.id)
    # print(user.liked)
    # print(user.disliked)
    await check_vacancies(config.bot.token)


from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession


# Мост для кнопки "Найти вакансии"
@router.callback_query(F.data == "start_search_vacancies")
async def callback_start_search(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
):
    await callback.answer()
    await finder(
        message=callback.message,
        session=session,
        state=state,
        tg_id=callback.from_user.id,
    )


# Мост для кнопки "Избранное"
@router.callback_query(F.data == "menu_open_history")
async def callback_open_history(callback: CallbackQuery, session: AsyncSession):
    await callback.answer()

    await show_all_history_messages(
        message=callback.message, session=session, tg_id=callback.from_user.id
    )


# Мост для кнопки "Фильтры"
@router.callback_query(F.data == "menu_open_filters")
async def callback_open_filters(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
):
    await callback.answer()

    await show_filters(
        message=callback.message,
        state=state,
        session=session,
        tg_id=callback.from_user.id,
    )


# Мост для кнопки "Справка"
@router.callback_query(F.data == "menu_open_help")
async def callback_open_help(callback: CallbackQuery):
    await callback.answer()
    help_text = (
        "❓ **Справка по боту:**\n\n"
        "1. Используйте команду /show_filters чтобы задать базовые параметры.\n"
        "2. Команда /finder включает режим 'Тиндера'.\n"
        "3. Кнопка 'Лайк' обучает бота продвигать вакансии с такими тегами вверх.\n"
        "4. Кнопка 'Скип' штрафует схожие технологии и опускает вакансии в конец ленты."
    )
    await callback.message.answer(help_text, parse_mode="Markdown")


@router.message(Command("help"))
async def help(message: Message) -> None:
    await message.answer("доступные команды........")
