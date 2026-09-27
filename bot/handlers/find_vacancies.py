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
    # Возвращаем полноценную клавиатуру с кнопкой "Назад", "Далее" и реакциями
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="❤️ Лайк", callback_data=f"like_{id_vac}"),
                InlineKeyboardButton(text="❌ Скип", callback_data=f"skip_{id_vac}"),
            ],
            [
                InlineKeyboardButton(text="⏪ Назад", callback_data="prev_vacancy"),
                InlineKeyboardButton(text="➡️ Далее", callback_data="next_vacancy"),
            ],
            [
                InlineKeyboardButton(text="Отмена", callback_data="cancel_vacancy_menu"),
            ],
        ]
    )
    return keyboard


async def render_vacancy_card(message: Message, state: FSMContext, session: AsyncSession, http_session: aiohttp.ClientSession, target_index: int, vacancies: list):
    current_vac = vacancies[target_index]
    vac_score = current_vac.get("calculated_score", 0)
    
    # Генерируем карточку
    vac_data = await HHAPI.format_vacancies(current_vac, score=vac_score, http_session=http_session)

    page_info = f"🗂 Вакансия {target_index + 1} из {len(vacancies)}"
    html_with_counter = vac_data["html_content"] + f"<br><footer>{page_info}</footer>"
    rich_message = InputRichMessage(html=html_with_counter)

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

        from bot.db.repos.repo_filters import get_user_filters
        db_filters = await get_user_filters(session, tg_id)
        user_filters = db_filters or {}
        await state.update_data(filters=user_filters)

        params = await filters_to_params_hh_api(tg_id, session, page=0)
        response = await HHAPI.search_vacancies(
            params, config.access_token.access_token, session, http_session=http_session, tg_id=tg_id
        )

        vacancies = response.get("items", [])
        user = await get_user(session, tg_id)

        if not vacancies:
            await message.answer("По вашим фильтрам ничего не найдено. Попробуйте изменить стек или грейд. 🔍")
            return

        filtered_vacancies = []
        for vac in vacancies:
            score = await HHAPI.personalize_score_safe(
                vac, user.skills or [], user.disliked or [], user.liked or [], user_filters=user_filters
            )
            if score != -999:
                vac["calculated_score"] = score
                filtered_vacancies.append(vac)

        vacancies = filtered_vacancies

        if not vacancies:
            await message.answer("По вашим фильтрам ничего не найдено (вакансии отсеяны по стеку). 🔍")
            return

        vacancies.sort(key=lambda x: x.get("calculated_score", 0), reverse=True)

        await state.update_data(vacancies=vacancies, current_index=0, api_page=0)
        await state.set_state(VacancySearch.browsing)

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
    tg_id = callback.from_user.id

    # Подгружаем актуальные фильтры и юзера из БД при каждом действии
    from bot.db.repos.repo_filters import get_user_filters
    user_filters = await get_user_filters(session, tg_id) or {}
    user = await get_user(session, tg_id)
    await state.update_data(filters=user_filters)

    # 1. ОБРАБОТКА ОТМЕНЫ
    if callback.data == "cancel_vacancy_menu":
        from bot.services.main_menu import send_main_menu
        await callback.answer("Возврат в меню")
        await state.clear()
        await send_main_menu(event=callback, edit=True, session=session)
        return

    # 2. ОБРАБОТКА КНОПКИ НАЗАД
    if callback.data == "prev_vacancy":
        await callback.answer()
        new_index = current_index - 1
        if new_index < 0:
            await callback.answer("⏪ Это самая первая вакансия!", show_alert=True)
            return
        
        # Пересчитываем скоринг для предыдущей вакансии на лету (если фильтры сменились)
        prev_vac = vacancies[new_index]
        score = await HHAPI.personalize_score_safe(prev_vac, user.skills or [], user.disliked or [], user.liked or [], user_filters=user_filters)
        prev_vac["calculated_score"] = score

        await state.update_data(current_index=new_index)
        await render_vacancy_card(callback.message, state, session, http_session, new_index, vacancies)
        return


    print(current_index)
    print(vacancies[current_index])
    # 3. ОБРАБОТКА ЛАЙКОВ / СКИПОВ (Если это были они)
    if callback.data.startswith("like_"):

        await callback.answer("Добавлено в Избранное! ❤️")
        vac_id = vacancies[current_index].get("id", "")
        key_skills = await HHAPI.get_key_skills_vac(vac_id,config.access_token.access_token, http_session)
        print(key_skills)
        await add_vacancy_action(session, tg_id, vacancies[current_index], "like", key_skills)
        
    elif callback.data.startswith("skip_"):

        await callback.answer("Вакансия пропущена ❌")
        vac_id = vacancies[current_index].get("id", "")
        key_skills = await HHAPI.get_key_skills_vac(vac_id,config.access_token.access_token, http_session)
        print(key_skills)
        await add_vacancy_action(session, tg_id, vacancies[current_index], "skip")


    # 4. ЛИСТАНИЕ ВПЕРЕД (Срабатывает при клике на "Далее", "Лайк" или "Скип")
    if callback.data == "next_vacancy" or callback.data.startswith("like_") or callback.data.startswith("skip_"):
        next_index = current_index + 1
        current_api_page = user_data.get("api_page", 0)

        # Цикл поиска следующей подходящей вакансии
        while True:
            # Если закончились вакансии на текущей странице, качаем следующую с HH
            if next_index >= len(vacancies):
                current_api_page += 1
                await callback.answer("Загружаю следующую страницу... 🔄")

                params = await filters_to_params_hh_api(tg_id, session, page=current_api_page)
                response = await HHAPI.search_vacancies(params, config.access_token.access_token, session, http_session, tg_id)
                new_vacancies = response.get("items", [])

                if not new_vacancies:
                    await callback.message.answer("🎉 Вы просмотрели абсолютно все вакансии по вашему стеку!")
                    await state.clear()
                    return

                # Фильтруем новую страницу по стеку
                filtered_new = []
                for vac in new_vacancies:
                    score = await HHAPI.personalize_score_safe(vac, user.skills or [], user.disliked or [], user.liked or [], user_filters=user_filters)
                    if score != -999:
                        vac["calculated_score"] = score
                        filtered_new.append(vac)

                if not filtered_new:
                    # Если вся страница отсеялась, шагаем по циклу дальше качать следующую страницу HH
                    next_index = 0
                    vacancies = []
                    continue

                filtered_new.sort(key=lambda x: x.get("calculated_score", 0), reverse=True)
                vacancies = filtered_new
                next_index = 0
                await state.update_data(vacancies=vacancies, api_page=current_api_page)

            # Берем карточку-кандидата для проверки
            candidate_vac = vacancies[next_index]
            
            # Считаем актуальный скоринг ПЕРЕД рендером
            score = await HHAPI.personalize_score_safe(
                candidate_vac, user.skills or [], user.disliked or [], user.liked or [], user_filters=user_filters
            )

            # Если на лету из-за смены фильтра вакансия перестала проходить порог стека, скипаем её автоматом
            if score == -999:
                next_index += 1
                continue
            
            candidate_vac["calculated_score"] = score
            break

        # Записываем обновленные индексы и рендерим
        await state.update_data(current_index=next_index, vacancies=vacancies)
        await render_vacancy_card(callback.message, state, session, http_session, next_index, vacancies)
    else:
        # Для неизвестных колбэков просто гасим часики
        await callback.answer()
