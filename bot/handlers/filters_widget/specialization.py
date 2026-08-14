from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.keyboard.filter_keyboard import get_filters_keyboard
from bot.states.filter_states import FilterForm

specialization_router = Router(name="specialization_widget")


async def show_specialization_filter_dialog(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    filters = data.get("filters", {})
    specialization = filters.get("specialization", [])  

    buttons = [
        [InlineKeyboardButton(text="🔙 Назад", callback_data="specialization_back")]
    ]

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text("Настройка специализации:", reply_markup=keyboard)

    prompt_message = await callback.message.answer(
        "Введите вашу специализацию (например, Python разработчик)"
    )
    await state.update_data(expecting="specialization")

    await state.update_data(
        prompt_message_id=prompt_message.message_id, expecting="specialization"
    )
    await state.set_state(FilterForm.waiting_for_input)
    await callback.answer()


@specialization_router.message(FilterForm.waiting_for_input)
async def specialization_input(state: FSMContext, message: Message):
    data = await state.get_data()
    if data.get("expecting") != "specialization":
        return
    specialization = message.text.strip()
    if not specialization:
        await message.answer("Специализация не может быть пустой")

    filters = data.get("filters", {})

    filters["specialization"] = specialization

    await state.update_data(filters=filters)

    # Удаляем сообщение с запросом ввода
    prompt_id = data.get("prompt_message_id")
    if prompt_id:
        try:
            await message.bot.delete_message(
                chat_id=message.chat.id, message_id=prompt_id
            )
        except:
            pass

    keyboard = get_filters_keyboard(filters)
    await message.answer("🔍 Настройки фильтрации:", reply_markup=keyboard)
    await state.set_state(None)


@specialization_router.callback_query(lambda c: c.data == "specialization_back")
async def specialization_back(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    filters = data.get("filters", {})
    keyboard = get_filters_keyboard(filters)
    await callback.message.edit_text("🔍 Настройки фильтрации:", reply_markup=keyboard)
    await state.set_state(FilterForm.waiting_for_input)

    # Удаляем сообщение с запросом ввода (если есть)
    prompt_id = data.get("prompt_message_id")
    if prompt_id:
        try:
            await callback.bot.delete_message(
                chat_id=callback.message.chat.id, message_id=prompt_id
            )
        except:
            pass

    await callback.answer()
