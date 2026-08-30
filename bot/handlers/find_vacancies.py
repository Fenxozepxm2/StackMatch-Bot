import traceback
import aiohttp
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


@router.message(Command("finder"))
async def finder(
    message: Message, session: AsyncSession, http_session: aiohttp.ClientSession ,state: FSMContext, tg_id: int | None = None
):
    try:
        params = await filters_to_params_hh_api(tg_id, session, page=0)
        response = await HHAPI.search_vacancies(
            params, config.access_token.access_token, session, http_session=http_session, tg_id=tg_id
        )

        vacancies = response.get("items", [])

        if not tg_id:
            tg_id = message.from_user.id

        user = await get_user(session, tg_id)
        await message.answer(f"ты {user.name}")

        if not vacancies:
            await message.answer("По вашим фильтрам ничего не найдено. 🔍")
            return

        for vac in vacancies:
            vac["calculated_score"] = await HHAPI.personalize_score_safe(
                vac, user.skills, user.disliked, user.liked
            )

        # Сортируем список по ключу "calculated_score"
        vacancies.sort(key=lambda x: x.get("calculated_score", 0), reverse=True)

        await state.update_data(vacancies=vacancies, current_index=0)
        await state.set_state(VacancySearch.browsing)

        first_item = vacancies[0]
        vac_score = first_item.get("calculated_score", 0)

        vac_data = await HHAPI.format_vacancies(first_item, score=vac_score)

        first_page_info = f"🗂 Вакансия 1 из {len(vacancies)}"
        html_with_counter = (
            vac_data["html_content"] + f"<br><footer>{first_page_info}</footer>"
        )

        rich_message = InputRichMessage(html=html_with_counter)

        await message.answer_rich(
            rich_message=rich_message,
            reply_markup=get_vacancy_keyboard(vac_data["id_vac"]),
        )

    except Exception as e:
        traceback.print_exc()
        error_msg = str(e)[:200]
        await message.answer(f"❌ Ошибка при поиске вакансий: {error_msg}")


@router.callback_query(VacancySearch.browsing)
async def process_vacancy_action(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, http_session: aiohttp.ClientSession
):
    user_data = await state.get_data()
    vacancies = user_data.get("vacancies", [])
    current_index = user_data.get("current_index", 0)

    if current_index >= len(vacancies):
        await callback.answer("Все вакансии уже просмотрены.")
        return

    current_vac = vacancies[current_index]

    # ОБРАБОТКА ЛАЙКА / СКИПА / ОТМЕНЫ
    if callback.data.startswith("like_"):
        vac_id = callback.data.split("_")[1]
        key_skills = await HHAPI.full_vacanci_id(
            vac_id, config.access_token.access_token, http_session
        )
        success = await add_vacancy_action(
            session,
            callback.from_user.id,
            current_vac,
            action="like",
            key_skills=key_skills,
        )
        if success:
            await callback.answer("Вакансия добавлена в избранное! ❤️")
        else:
            await callback.answer("Вы уже лайкали эту вакансию ранее.")

    elif callback.data.startswith("skip_"):
        vac_id = callback.data.split("_")[1]
        key_skills = await HHAPI.full_vacanci_id(
            vac_id, config.access_token.access_token, http_session
        )
        success = await add_vacancy_action(
            session,
            callback.from_user.id,
            current_vac,
            action="skip",
            key_skills=key_skills,
        )
        if success:
            await callback.answer("Вакансия пропущена ❌")
        else:
            await callback.answer("Вы уже пропускали эту вакансию ранее.")

    elif callback.data == "cancel_vacancy_menu":
        from bot.services.main_menu import send_main_menu
        await callback.answer("Вы вернулись в главное меню")
        await state.clear()
        await send_main_menu(event=callback, edit=True, session=session)
        return
    
    elif callback.data == "next_vacancy":
        await callback.answer()
    else:
        await callback.answer()
        return

    user = await get_user(session, callback.from_user.id)

    await session.refresh(user, ["liked", "disliked"])

    next_index = current_index + 1

    if next_index >= len(vacancies):
        # Если пачка закончилась, запрашиваем новую страницу из API hh.ru
        current_api_page = user_data.get("api_page", 0)
        next_api_page = current_api_page + 1

        await callback.answer("Загружаю новые вакансии... 🔄")

        params = await filters_to_params_hh_api(
            callback.from_user.id, session, page=next_api_page
        )

        response = await HHAPI.search_vacancies(
            params=params,
            access_token=config.access_token.access_token,
            session=session,
            http_session=http_session,
            tg_id=callback.from_user.id,
        )

        new_vacancies = response.get("items", [])

        if not new_vacancies:
            await callback.message.answer(
                "🎉 Вы просмотрели абсолютно все существующие вакансии по вашим фильтрам!"
            )
            await state.clear()
            return

        # Ранжируем новую пачку первый раз
        for vac in new_vacancies:
            vac["calculated_score"] = await HHAPI.personalize_score_safe(
                vac, user.skills or [], user.disliked or [], user.liked or []
            )
        new_vacancies.sort(key=lambda x: x.get("calculated_score", 0), reverse=True)

        next_index = 0
        vacancies = new_vacancies
        await state.update_data(
            vacancies=vacancies, current_index=next_index, api_page=next_api_page
        )
    else:
        # Если идем по текущей пачке, просто сохраняем новый индекс
        await state.update_data(current_index=next_index)

    next_item = vacancies[next_index]
    
    next_item["calculated_score"] = await HHAPI.personalize_score_safe(
        next_item, user.skills or [], user.disliked or [], user.liked or []
    )
    
    vacancies[next_index] = next_item
    await state.update_data(vacancies=vacancies)

    item_score = next_item.get("calculated_score", 0)

    vac_data = await HHAPI.format_vacancies(next_item, score=item_score)

    page_info = f"🗂 Вакансия {next_index + 1} из {len(vacancies)}"
    html_with_counter = vac_data["html_content"] + f"<br><footer>{page_info}</footer>"

    rich_message = InputRichMessage(html=html_with_counter)

    try:
        await callback.message.edit_text(
            rich_message=rich_message,
            reply_markup=get_vacancy_keyboard(vac_data["id_vac"]),
        )
    except Exception:
        traceback.print_exc()
        await callback.message.answer("❌ Произошла ошибка при обновлении вакансии.")



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
