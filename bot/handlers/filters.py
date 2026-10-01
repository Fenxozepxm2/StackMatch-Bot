from bot.services.main_menu import send_main_menu
import structlog
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputRichMessage,
)
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import *
from bot.db.repos.repo_filters import get_user_filters, save_filters
from bot.db.repos.repo_user import save_user
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

@router.message(F.text.startswith("добавить_стек:"))
async def process_added_inline_tech(message: Message, state: FSMContext):
    new_tech = message.text.replace("добавить_стек:", "").strip()
    
    state_data = await state.get_data()
    filters = state_data.get("filters", {})
    current_stack = filters.get("user_tech_stack", [])
    
    if new_tech not in current_stack:
        current_stack.append(new_tech)
        filters["user_tech_stack"] = current_stack
        await state.update_data(filters=filters)
    
    await message.delete()
    await state.update_data(expecting="tech_stack")
    
    save_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⌨️ Выбрать еще навык", switch_inline_query_current_chat="stack: ")
            ],
            [
                InlineKeyboardButton(text="🟢 Завершить и сохранить стек", callback_data="finish_tech_stack")
            ]
        ]
    )

    await message.answer(
        f"➕ Добавлено: <code>{new_tech}</code>\n"
        f"📋 Весь стек: <code>{', '.join(current_stack)}</code>\n\n"
        f"<i>Вы можете продолжить выбор или нажать кнопку ниже для сохранения:</i>",
        parse_mode="HTML",
        reply_markup=save_keyboard
    )




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
    elif expecting == "tech_stack":
        text = message.text.strip()
        if not text:
            await message.answer("Стек не может быть пустым.")
            return

        # Разрезаем строку по запятым, чистим пробелы вокруг слов и убираем пустышки
        new_technologies = [word.strip() for word in text.split(",") if word.strip()]

        if not new_technologies:
            await message.answer("Не удалось распознать технологии. Напишите их через запятую.")
            return

        filters = data.get("filters", {})
        current_stack = filters.get("user_tech_stack", [])

        # Пакетное добавление с защитой от дублирования
        added_count = 0
        for tech in new_technologies:
            # Приводим к красивому регистру (первая буква заглавная, например fastapi -> Fastapi)
            # Но для аббревиатур вроде API, gRPC, CI/CD лучше оставить оригинальный ввод пользователя,
            # поэтому возьмем просто исходное слово, убрав лишние символы
            formatted_tech = tech.strip(",. ")
            
            if formatted_tech and formatted_tech not in current_stack:
                current_stack.append(formatted_tech)
                added_count += 1

        filters["user_tech_stack"] = current_stack
        await state.update_data(filters=filters, expecting=None)
        await state.set_state(None) # Сбрасываем стейт ввода

        # Генерируем обновленную клавиатуру
        keyboard = get_filters_keyboard(filters)
        
        await message.answer(
            f"✅ Успешно добавлено технологий: <b>{added_count}</b>\n"
            f"📦 Текущий стек: <code>{', '.join(current_stack)}</code>", 
            parse_mode="HTML"
        )
        await message.answer("🔍 Настройки фильтрации:", reply_markup=keyboard)

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
    await send_main_menu(event=callback, session=session, edit=False)


@router.message(Command("show_filters"))
async def show_filters(
    message: Message, state: FSMContext, session: AsyncSession, tg_id: int = None
):

    if tg_id is None:
        tg_id = message.from_user.id


    await save_user(session, tg_id, message.from_user.username)
    
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


@router.callback_query(lambda c: c.data == "toggle_strict_stack")
async def callback_toggle_strict_stack(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    filters = data.get("filters", {})
    
    filters["strict_stack_filter"] = not filters.get("strict_stack_filter", False)
    
    await state.update_data(filters=filters)
    await callback.message.edit_reply_markup(reply_markup=get_filters_keyboard(filters))



@router.callback_query(lambda c: c.data == "edit_tech_stack")
async def start_tech_stack_changing(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    await state.update_data(expecting="tech_stack")
    
    inline_hint_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⌨️ Помощник автодополнения (по одной)", 
                    switch_inline_query_current_chat="stack: "
                )
                
            ],
            [InlineKeyboardButton(text="Очистить", callback_data="remove_stack")]
        ]
    )
    
    hint_text = (
        "🚀 <b>Настройка твоего IT-стека</b>\n\n"
        "Вы можете ввести список технологий <b>одним сообщением через запятую</b>.\n"
        "<i>Пример: Python, FastAPI, PostgreSQL, Docker, Git</i>\n\n"
        "💡 Или нажмите кнопку ниже, чтобы использовать интерактивный помощник автодополнения слов.\n\n"
        "<b>Отправьте ваш стек сообщением в чат:</b>"
    )
    
    await callback.message.answer(text=hint_text, parse_mode="HTML", reply_markup=inline_hint_keyboard)


@router.callback_query(lambda c: c.data == "remove_stack")
async def remove_stack_filter(callback: CallbackQuery, state: FSMContext):
    # 1. Выдаем всплывающее уведомление в Телеграме, что стек очищен
    await callback.answer("Стек технологий полностью сброшен! 🧹")
    
    # 2. Вытаскиваем текущие данные из состояния
    state_data = await state.get_data()
    filters = state_data.get("filters", {})
    
    # 3. Полностью вычищаем ключи нашего ИТ-стека
    filters["user_tech_stack"] = []
    filters["strict_stack_filter"] = False # Отключаем жесткий фильтр совпадения
    
    # 4. Сохраняем обновленные пустые фильтры обратно в стейт оперативки
    await state.update_data(filters=filters)
    
    # 5. Мгновенно перерисовываем инлайн-кнопки на экране, чтобы обновить статус стека
    await callback.message.edit_reply_markup(
        reply_markup=get_filters_keyboard(filters)
    )


    



@router.callback_query(lambda c: c.data == "finish_tech_stack")
async def callback_finish_tech_stack(callback: CallbackQuery, state: FSMContext):
    await callback.answer("Стек успешно сохранен! 🚀")
    
    # Полностью сбрасываем флаги ожидания текста
    await state.update_data(expecting=None)
    
    state_data = await state.get_data()
    filters = state_data.get("filters", {})
    
    # Удаляем промежуточное сообщение с кнопками, чтобы не захламлять чат
    await callback.message.delete()
    
    # Возвращаем главное окно настроек с обновленными данными
    keyboard = get_filters_keyboard(filters)
    await callback.message.answer("🔍 Настройки фильтрации:", reply_markup=keyboard)



@router.callback_query(lambda c: c.data == "toggle_currency")
async def callback_toggle_currency(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    filters = data.get("filters", {})
    
    # Ротируем валюту по кругу при каждом клике
    current_currency = filters.get("currency", "RUR")
    currency_cycle = {"RUR": "USD", "USD": "EUR", "EUR": "RUR"}
    filters["currency"] = currency_cycle.get(current_currency, "RUR")
    
    await state.update_data(filters=filters)
    await callback.message.edit_reply_markup(reply_markup=get_filters_keyboard(filters))
