# bot/handlers/filter_widgets/schedule.py
from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from bot.handlers.filters_widget.base import build_choice_keyboard
from bot.keyboard.filter_keyboard import get_filters_keyboard
from bot.states.filter_states import FilterForm

schedule_router = Router(name="schedule_widget")

SCHEDULE_OPTIONS = [
    "5/2",
    "2/2",
    "3/3",
    "Свободный",
    "6/1",
    "4/2",
    "3/2",
    "4/3",
    "4/4",
    "1/3",
    "2/1",
    "1/2",
]


async def show_schedule_choices(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    filters = data.get("filters", {})
    current = filters.get("schedule", [])

    # общая функция для создания клавиатуры
    keyboard = await build_choice_keyboard(
        options=SCHEDULE_OPTIONS,
        current_selection=current,
        toggle_prefix="schedule_toggle",
        save_callback="schedule_save",
        cancel_callback="schedule_cancel",
    )

    await callback.answer()
    await callback.message.edit_text(
        "Выберите график работы (можно несколько):", reply_markup=keyboard
    )
    await state.set_state(FilterForm.choosing_schedule)


@schedule_router.callback_query(lambda c: c.data.startswith("schedule_toggle_"))
async def schedule_toggle(callback: CallbackQuery, state: FSMContext):
    option = callback.data.split("_", 2)[2]
    data = await state.get_data()
    filters = data.get("filters", {})
    current = filters.get("schedule", [])

    if option in current:
        current.remove(option)
    else:
        current.append(option)

    filters["schedule"] = current
    await state.update_data(filters=filters)
    await show_schedule_choices(callback, state)


@schedule_router.callback_query(lambda c: c.data == "schedule_save")
async def schedule_save(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    filters = data.get("filters", {})
    # Сохранять в БД пока не нужно, просто возвращаемся в главное меню
    await state.update_data(filters=filters, awaiting_field=None)
    # Показываем обновлённое главное меню
    keyboard = get_filters_keyboard(filters)
    await callback.answer("Фильтры сохранены")
    await callback.message.delete()
    await callback.message.answer("🔍 Настройки фильтрации:", reply_markup=keyboard)
    await state.set_state(FilterForm.waiting_for_input)  # или None
    await callback.answer()


@schedule_router.callback_query(lambda c: c.data == "schedule_cancel")
async def schedule_cancel(callback: CallbackQuery, state: FSMContext):
    # Возврат без сохранения изменений
    data = await state.get_data()
    filters = data.get("filters", {})
    keyboard = get_filters_keyboard(filters)
    await callback.answer()
    await callback.message.delete()
    await callback.message.answer("🔍 Настройки фильтрации:", reply_markup=keyboard)
    await state.set_state(FilterForm.waiting_for_input)
    await callback.answer()
