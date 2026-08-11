from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.keyboard.filter_keyboard import get_filters_keyboard
from bot.services.city_mapper import CityMapper
from bot.states.filter_states import FilterForm

city_router = Router(name="city_widget")


async def show_city_menu(callback: CallbackQuery, state: FSMContext):
    """Показывает меню управления городом."""
    data = await state.get_data()
    filters = data.get("filters", {})
    current_city = filters.get("city")

    text = f"🏙 Город: {current_city if current_city else 'не задан'}"
    buttons = [
        [InlineKeyboardButton(text="✏️ Изменить город", callback_data="change_city")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="city_back_to_main")],
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@city_router.callback_query(lambda c: c.data == "edit_city")
async def edit_city_callback(callback: CallbackQuery, state: FSMContext):
    await show_city_menu(callback, state)


@city_router.callback_query(lambda c: c.data == "change_city")
async def change_city(callback: CallbackQuery, state: FSMContext):
    """Переключает в режим ввода города (поиск подсказок)."""
    await state.update_data(expecting="city_input")
    await state.set_state(FilterForm.waiting_for_input)
    await callback.message.answer(
        "Напишите название города (можно сокращённо, например, спб):"
    )
    await callback.answer()


@city_router.message(FilterForm.waiting_for_input)
async def process_city_input(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("expecting") != "city_input":
        return
    query = message.text.strip()
    if not query:
        await message.answer("Название города не может быть пустым")
        return

    found = CityMapper.search_cities(query, limit=10)

    valid_cities = [c for c in found if c and c.strip() and c.strip() != "."]

    if not valid_cities:
        await message.answer(
            "Город не найден. Попробуйте ещё раз или введите полное название."
        )
        return

    buttons = []
    for city_name in valid_cities:
        display_name = city_name
        short_name = city_name[:15].strip()

        if not short_name:
            continue

        buttons.append(
            [
                InlineKeyboardButton(
                    text=display_name, callback_data=f"select_city_{short_name}"
                )
            ]
        )

    buttons.append(
        [InlineKeyboardButton(text="🔙 Отмена", callback_data="cancel_city_input")]
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    prompt_id = data.get("prompt_message_id")
    if prompt_id:
        try:
            await message.bot.delete_message(
                chat_id=message.chat.id, message_id=prompt_id
            )
        except:
            pass

    sent_msg = await message.answer("Выберите город из списка:", reply_markup=keyboard)
    await state.update_data(
        prompt_message_id=sent_msg.message_id, expecting="city_input"
    )


@city_router.callback_query(lambda c: c.data.startswith("select_city_"))
async def select_city(callback: CallbackQuery, state: FSMContext):
    city_name = callback.data.split("_", 2)[2]
    data = await state.get_data()
    filters = data.get("filters", {})
    filters["city"] = city_name
    await state.update_data(filters=filters, expecting=None, prompt_message_id=None)
    await state.set_state(None)
    # Убираем удаление, просто показываем меню города на том же сообщении
    await show_city_menu(callback, state)


@city_router.callback_query(lambda c: c.data == "cancel_city_input")
async def cancel_city_input(callback: CallbackQuery, state: FSMContext):
    await state.update_data(expecting=None, prompt_message_id=None)
    await state.set_state(None)
    # Не удаляем, а редактируем текущее сообщение
    await show_city_menu(callback, state)


@city_router.callback_query(lambda c: c.data == "city_back_to_main")
async def city_back_to_main(callback: CallbackQuery, state: FSMContext):
    """Возврат в главное меню фильтров."""
    data = await state.get_data()
    filters = data.get("filters", {})
    keyboard = get_filters_keyboard(filters)
    await callback.message.edit_text("🔍 Настройки фильтрации:", reply_markup=keyboard)
    await state.set_state(FilterForm.waiting_for_input)
    await callback.answer()
