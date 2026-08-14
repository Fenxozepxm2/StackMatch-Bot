from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from bot.handlers.filters_widget.base import build_choice_keyboard
from bot.keyboard.filter_keyboard import get_filters_keyboard
from bot.states.filter_states import FilterForm

workformat_router = Router(name="workformat_widget")

workformat_options = [
    "На месте работодателя",
    "Удалённо",
    "Гибрид",
    "Разъездной",
]


async def show_workformat_choices(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    filters = data.get("filters", {})
    current = filters.get("workformat", [])

    # общая функция для создания клавиатуры
    keyboard = await build_choice_keyboard(
        options=workformat_options,
        current_selection=current,
        toggle_prefix="workformat_toggle",
        save_callback="workformat_save",
        cancel_callback="workformat_cancel",
    )

    await callback.answer()
    await callback.message.edit_text(
        "Выберите формат работы работы (можно несколько):", reply_markup=keyboard
    )
    await state.set_state(FilterForm.choosing_workformat)


@workformat_router.callback_query(lambda c: c.data.startswith("workformat_toggle_"))
async def workformat_toggle(callback: CallbackQuery, state: FSMContext):
    option = callback.data.split("_", 2)[2]
    data = await state.get_data()
    filters = data.get("filters", {})
    current = filters.get("workformat", [])

    if option in current:
        current.remove(option)
    else:
        current.append(option)

    filters["workformat"] = current
    await state.update_data(filters=filters)
    await show_workformat_choices(callback, state)


@workformat_router.callback_query(lambda c: c.data == "workformat_save")
async def workformat_save(callback: CallbackQuery, state: FSMContext):
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


@workformat_router.callback_query(lambda c: c.data == "workformat_cancel")
async def workformat_cancel(callback: CallbackQuery, state: FSMContext):
    # Возврат без сохранения изменений
    data = await state.get_data()
    filters = data.get("filters", {})
    keyboard = get_filters_keyboard(filters)
    await callback.answer()
    await callback.message.delete()
    await callback.message.answer("🔍 Настройки фильтрации:", reply_markup=keyboard)
    await state.set_state(FilterForm.waiting_for_input)
    await callback.answer()
