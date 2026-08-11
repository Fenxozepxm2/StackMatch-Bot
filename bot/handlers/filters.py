import structlog
from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import *
from bot.db.repos.repo_filters import get_user_filters, save_filters
from bot.handlers.filters_widget import (
    city,
    exclude_keyword,
    exp,
    keywords,
    salary,
    schedule,
    specialization,
    work_format,
)
from bot.keyboard.filter_keyboard import get_filters_keyboard
from bot.states.filter_states import FilterForm

logger = structlog.get_logger(__name__)
router = Router(name="Filters")

router.include_router(schedule.schedule_router)
router.include_router(exp.exp_router)
router.include_router(city.city_router)
router.include_router(salary.salary_router)
router.include_router(work_format.workformat_router)
router.include_router(specialization.specialization_router)
router.include_router(keywords.keywords_router)
router.include_router(exclude_keyword.exclude_keywords_router)


# class FilterForm(StatesGroup):
#     city = State()
#     salary = State()
#     specialization = State()
#     payday = State()
#     exp = State()
#     employmentZan = State()
#     schedule = State()
#     work_hours = State()
#     work_format = State()
#     newest_first = State()
#     employment_type = State()
#     waiting_for_input = State()
#     choosing_shedule = State()
#     choosing_exp = State()


@router.message(FilterForm.waiting_for_input)
async def universal_text_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    expecting = data.get("expecting")

    if expecting == "salary":
        text = message.text.strip().lower()
        salary_from = None
        salary_to = None
        try:
            if "-" in text:
                parts = text.split("-")
                salary_from = int("".join(filter(str.isdigit, parts[0])))
                salary_to = int("".join(filter(str.isdigit, parts[1])))
            elif "от" in text:
                salary_from = int("".join(filter(str.isdigit, text.replace("от", ""))))
            elif "до" in text:
                salary_to = int("".join(filter(str.isdigit, text.replace("до", ""))))
            else:
                salary_from = int("".join(filter(str.isdigit, text)))
        except ValueError:
            await message.answer("Ошибка. Введи только цифры, например: 70000-120000")
            return

        # Проверяем, что оба значения есть, и только тогда сравниваем
        if (
            salary_from is not None
            and salary_to is not None
            and salary_from > salary_to
        ):
            await message.answer(
                "Введите корректный диапазон (минимальное значение не может быть больше максимального)"
            )
            return

        filters = data.get("filters", {})
        filters["salary_from"] = salary_from
        filters["salary_to"] = salary_to
        await state.update_data(filters=filters, expecting=None)
        await state.set_state(None)
        keyboard = get_filters_keyboard(filters)
        await message.answer("🔍 Настройки фильтрации:", reply_markup=keyboard)

    elif expecting == "city_input":
        from bot.handlers.filters_widget.city import process_city_input

        try:
            await process_city_input(message, state)
        except ValueError:
            await message.answer("ожидается сущетвующий город России")
            return

    elif expecting == "specialization":
        from bot.handlers.filters_widget.specialization import specialization_input

        await specialization_input(state, message)

    elif expecting == "keyword":
        from bot.handlers.filters_widget.keywords import process_keyword_input

        await process_keyword_input(message, state)
    elif expecting == "exclude_keywords":
        from bot.handlers.filters_widget.exclude_keyword import (
            process_exclude_keywords_input,
        )

        await process_exclude_keywords_input(message, state)

    else:
        await message.answer("Я не ожидаю текст. Используйте кнопки.")


@router.callback_query(lambda c: c.data == "close_filters")
async def close_and_save_filters(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
):
    state_data = await state.get_data()
    new_filters = state_data.get("filters", {})
    tg_id = callback.from_user.id
    await save_filters(session, new_filters, tg_id)

    print(new_filters)

    await callback.answer()
    await state.clear()
    await callback.message.delete()


@router.message(Command("show_filters"))
async def show_filters(
    message: Message, state: FSMContext, session: AsyncSession, tg_id: int
):

    # Получаем словарь с фильтрами (если нет — пустой)
    filters_dict = await get_user_filters(session, tg_id)

    # Сохраняем фильтры в состояние (если нужно для следующих шагов редактирования)
    await state.update_data(filters=filters_dict)
    await state.set_state(FilterForm.waiting_for_input)

    # Генерируем клавиатуру
    keyboard = get_filters_keyboard(filters_dict)
    await message.answer("🔍 Настройки фильтрации:", reply_markup=keyboard)


@router.callback_query(lambda c: c.data.startswith("edit_exp"))
async def start_exp_changing(callback: CallbackQuery, state: FSMContext):
    from bot.handlers.filters_widget.exp import show_exp_choise

    await show_exp_choise(callback, state)


@router.callback_query(lambda c: c.data.startswith("edit_schedule"))
async def start_shedule_changing(callback: CallbackQuery, state: FSMContext):
    from bot.handlers.filters_widget.schedule import show_schedule_choices

    await show_schedule_choices(callback, state)


@router.callback_query(lambda c: c.data.startswith("edit_city"))
async def start_city_changing(callback: CallbackQuery, state: FSMContext):
    from bot.handlers.filters_widget.city import show_city_menu

    await show_city_menu(callback, state)


@router.callback_query(lambda c: c.data.startswith("edit_salary"))
async def start_salary_changing(callback: CallbackQuery, state: FSMContext):
    from bot.handlers.filters_widget.salary import show_salary_dialog

    await show_salary_dialog(callback, state)


@router.callback_query(lambda c: c.data.startswith("edit_work_format"))
async def start_workformat_changing(callback: CallbackQuery, state: FSMContext):
    from bot.handlers.filters_widget.work_format import show_workformat_choices

    await show_workformat_choices(callback, state)


@router.callback_query(lambda c: c.data.startswith("edit_specialization"))
async def start_specialization_changing(callback: CallbackQuery, state: FSMContext):
    from bot.handlers.filters_widget.specialization import (
        show_specialization_filter_dialog,
    )

    await show_specialization_filter_dialog(callback, state)


@router.callback_query(lambda c: c.data.startswith("edit_keywords"))
async def start_keywords_changing(callback: CallbackQuery, state: FSMContext):
    from bot.handlers.filters_widget.keywords import show_keywords_menu

    await show_keywords_menu(callback, state)


@router.callback_query(lambda c: c.data.startswith("edit_exclude"))
async def start_exclude_keywords_changing(callback: CallbackQuery, state: FSMContext):
    from bot.handlers.filters_widget.exclude_keyword import show_exclude_keywords_menu

    await show_exclude_keywords_menu(callback, state)
