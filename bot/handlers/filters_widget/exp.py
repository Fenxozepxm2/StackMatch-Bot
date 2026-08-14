from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from bot.handlers.filters_widget.base import build_choice_keyboard
from bot.keyboard.filter_keyboard import get_filters_keyboard
from bot.states.filter_states import FilterForm

exp_router = Router(name="exp_widget")

EXP_OPTIONS = ["Без опыта", "от 1 до 3", "от 3 до 6", "Более 6"]


async def show_exp_choise(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    filters = data.get("filters", {})
    current = filters.get("exp", [])

    # общая функция для создания клавиатуры
    keyboard = await build_choice_keyboard(
        options=EXP_OPTIONS,
        current_selection=current,
        toggle_prefix="exp_toggle",
        save_callback="exp_save",
        cancel_callback="exp_cancel",
    )

    await callback.answer()
    await callback.message.edit_text(
        "Выберите опыт работы (можно несколько):", reply_markup=keyboard
    )
    await state.set_state(FilterForm.choosing_exp)


@exp_router.callback_query(lambda c: c.data.startswith("exp_toggle_"))
async def exp_toggle(callback: CallbackQuery, state: FSMContext):

    option = callback.data.split("_", 2)[2]

    data = await state.get_data()
    filters = data.get("filters", {})
    current = filters.get("exp", [])

    if option in current:
        current.remove(option)
    else:
        current.append(option)

    filters["exp"] = current
    await state.update_data(filters=filters)
    await show_exp_choise(callback, state)


@exp_router.callback_query(lambda c: c.data == "exp_save")
async def exp_save(callback: CallbackQuery, state: FSMContext):
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


@exp_router.callback_query(lambda c: c.data == "exp_cancel")
async def exp_cancel(callback: CallbackQuery, state: FSMContext):
    # Возврат без сохранения изменений
    data = await state.get_data()
    filters = data.get("filters", {})
    keyboard = get_filters_keyboard(filters)
    await callback.answer()
    await callback.message.delete()
    await callback.message.answer("🔍 Настройки фильтрации:", reply_markup=keyboard)
    await state.set_state(FilterForm.waiting_for_input)
    await callback.answer()
