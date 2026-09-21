import traceback
import aiohttp
from bot.services.city_mapper import CityMapper
import structlog
from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputRichMessage,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import load_config
from bot.db.repos.repo_user import get_user
from bot.db.repos.repo_vacancies import add_vacancy_action
from bot.services.to_hhApi import HHAPI, filters_to_params_hh_api

config = load_config()

logger = structlog.get_logger(__name__)

router = Router(name="find_vacancies")


class VacancySearch(StatesGroup):
    browsing = State()


def get_vacancy_keyboard(id_vac: str) -> InlineKeyboardMarkup:
    # Передаем id_vac в callback_data, чтобы бот знал, какую именно вакансию лайкнули/пропустили
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="❤️ Лайк", callback_data=f"like_{id_vac}"),
                InlineKeyboardButton(text="❌ Скип", callback_data=f"skip_{id_vac}"),
            ],
            [
                InlineKeyboardButton(text="➡️ Далее", callback_data="next_vacancy"),
                InlineKeyboardButton(
                    text="Отмена", callback_data="cancel_vacancy_menu"
                ),
            ],
        ]
    )
    return keyboard


async def render_vacancy_card(message: Message, state: FSMContext, session: AsyncSession, http_session: aiohttp.ClientSession, target_index: int, vacancies: list):
    current_vac = vacancies[target_index]
    vac_score = current_vac.get("calculated_score", 0)
    
    # Генерируем карточку, передавая http_session для подгрузки <details>
    vac_data = await HHAPI.format_vacancies(current_vac, score=vac_score, http_session=http_session)

    page_info = f"🗂 Вакансия {target_index + 1} из {len(vacancies)}"
    html_with_counter = vac_data["html_content"] + f"<br><footer>{page_info}</footer>"
    rich_message = InputRichMessage(html=html_with_counter)

    # Если мы зашли через текстовую команду, отправляем новое сообщение, если через кнопку — редактируем старое
    try:
        if message.from_user.is_bot:
            await message.edit_text(rich_message=rich_message, reply_markup=get_vacancy_keyboard(vac_data["id_vac"]))
        else:
            await message.answer_rich(rich_message=rich_message, reply_markup=get_vacancy_keyboard(vac_data["id_vac"]))
    except Exception:
        traceback.print_exc()


@router.message(Command("finder"))
async def finder(
    message: Message, session: AsyncSession, http_session: aiohttp.ClientSession, state: FSMContext, tg_id: int | None = None
):
    try:
        if tg_id is None:
            tg_id = message.from_user.id

        # Подгружаем фильтры из базы в стейт, если человек зашел через текстовую команду /finder
        state_data = await state.get_data()
        if not state_data.get("filters"):
            from bot.db.repos.repo_filters import get_user_filters
            db_filters = await get_user_filters(session, tg_id)
            if db_filters:
                await state.update_data(filters=db_filters)

        params = await filters_to_params_hh_api(tg_id, session, page=0)
        response = await HHAPI.search_vacancies(
            params, config.access_token.access_token, session, http_session=http_session, tg_id=tg_id
        )

        vacancies = response.get("items", [])
        user = await get_user(session, tg_id)

        if not vacancies:
            await message.answer("По вашим фильтрам ничего не найдено. Попробуйте изменить стек или грейд. 🔍")
            return

        # Рассчитываем скоринг релевантности
        for vac in vacancies:
            vac["calculated_score"] = await HHAPI.personalize_score_safe(
                vac, user.skills, user.disliked, user.liked
            )

        vacancies.sort(key=lambda x: x.get("calculated_score", 0), reverse=True)

        await state.update_data(vacancies=vacancies, current_index=0, api_page=0)
        await state.set_state(VacancySearch.browsing)

        # Рендерим самую первую ИТ-карточку
        await render_vacancy_card(message, state, session, http_session, 0, vacancies)

    except Exception as e:
        traceback.print_exc()
        await message.answer(f"❌ Ошибка при поиске: {str(e)[:200]}")



@router.callback_query(VacancySearch.browsing)
async def process_vacancy_action(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, http_session: aiohttp.ClientSession
):
    user_data = await state.get_data()
    vacancies = user_data.get("vacancies", [])
    current_index = user_data.get("current_index", 0)

    # 1. ОБРАБОТКА КНОПКИ НАЗАД
    if callback.data == "prev_vacancy":
        await callback.answer()
        new_index = current_index - 1
        if new_index < 0:
            await callback.answer("⏪ Это самая первая вакансия!", show_alert=True)
            return
        await state.update_data(current_index=new_index)
        await render_vacancy_card(callback.message, state, session, http_session, new_index, vacancies)
        return

    # 2. ОБРАБОТКА ОТМЕНЫ
    if callback.data == "cancel_vacancy_menu":
        from bot.services.main_menu import send_main_menu
        await callback.answer("Возврат в меню")
        await state.clear()
        await send_main_menu(event=callback, edit=True, session=session)
        return

    if current_index >= len(vacancies):
        await callback.answer("Все вакансии просмотрены.")
        return

    current_vac = vacancies[current_index]

    # 3. ЛАЙК / СКИП
    if callback.data.startswith("like_"):
        await callback.answer("Добавлено в Избранное! ❤️")
        # Тут твоя функция сохранения лайка add_vacancy_action...
    elif callback.data.startswith("skip_"):
        await callback.answer("Вакансия пропущена ❌")
        # Тут твоя функция сохранения скипа...

    # Шаг вперед
    next_index = current_index + 1
    user = await get_user(session, callback.from_user.id)

    if next_index >= len(vacancies):
        current_api_page = user_data.get("api_page", 0)
        next_api_page = current_api_page + 1
        await callback.answer("Загружаю следующую страницу... 🔄")

        params = await filters_to_params_hh_api(callback.from_user.id, session, page=next_api_page)
        response = await HHAPI.search_vacancies(params, config.access_token.access_token, session, http_session, callback.from_user.id)
        new_vacancies = response.get("items", [])

        if not new_vacancies:
            await callback.message.answer("🎉 Вы просмотрели абсолютно все вакансии по вашему стеку!")
            await state.clear()
            return

        for vac in new_vacancies:
            vac["calculated_score"] = await HHAPI.personalize_score_safe(vac, user.skills, user.disliked, user.liked)
        new_vacancies.sort(key=lambda x: x.get("calculated_score", 0), reverse=True)

        next_index = 0
        vacancies = new_vacancies
        await state.update_data(vacancies=vacancies, current_index=next_index, api_page=next_api_page)
    else:
        await state.update_data(current_index=next_index)

    await render_vacancy_card(callback.message, state, session, http_session, next_index, vacancies)



@router.message(Command("get_vacancies"))
async def get_vacancies(message: Message, session: AsyncSession, http_session: aiohttp.ClientSession):

    try:
        # 1. Получаем сформированные параметры
        params = await filters_to_params_hh_api(message, session)

        # 2. Делаем запрос к HH
        response = await HHAPI.search_vacancies(
            params, config.access_token.access_token, http_session=http_session
        )

        # 3. Вытаскиваем список вакансий из ответа
        vacancies = response.get("items", [])

        if not vacancies:
            await message.answer("По вашим фильтрам ничего не найдено. ")
            return

        # 4. Собираем красивый текст ответа, укладываясь в лимиты
        text_parts = ["* Найдена свежая подборка вакансий:*\n"]

        for i, vac in enumerate(vacancies[:5], 1):  # Берем первые 5 вакансий для теста
            name = vac.get("name")
            company = vac.get("employer", {}).get("name", "Компания не указана")
            url = vac.get("alternate_url")

            # Красиво форматируем зарплату
            salary_data = vac.get("salary")
            salary_str = "не указана"
            if salary_data:
                sal_from = (
                    f"от {salary_data.get('from')}" if salary_data.get("from") else ""
                )
                sal_to = f"до {salary_data.get('to')}" if salary_data.get("to") else ""
                salary_str = (
                    f"{sal_from} {sal_to} {salary_data.get('currency')}".strip()
                )

            # Добавляем вакансию в список
            text_parts.append(
                f"{i}. *{name}*\n"
                f" 🏢 Компания: {company}\n"
                f" 💰 Зарплата: {salary_str}\n"
                f" 🔗 [Открыть вакансию]({url})\n"
            )

        # Объединяем части в одно сообщение
        final_text = "\n".join(text_parts)

        # Отправляем пользователю (используем Markdown, чтобы ссылки кликались)
        await message.answer(final_text, parse_mode="Markdown")

    except Exception as e:
        # Защита на случай ошибок: если текст ошибки слишком длинный, берем только первые 200 символов
        error_msg = str(e)[:200]
        await message.answer(f"❌ Ошибка при поиске вакансий: {error_msg}")
