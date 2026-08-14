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

exclude_keywords_router = Router(name="exclude_keywords_widget")


async def show_exclude_keywords_menu(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    filters = data.get("filters", {})
    exclude_keywords = filters.get("find_exclude_keywords", [])

    text = "❌ Исключающие ключевые слова:\n" + (
        "\n".join(exclude_keywords) if exclude_keywords else "(пусто)"
    )
    buttons = [
        [
            InlineKeyboardButton(
                text="➕ Добавить слово", callback_data="add_exclude_keywords"
            )
        ],
        [InlineKeyboardButton(text="✅ Готово", callback_data="exclude_keywords_done")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="exclude_keywords_back")],
    ]
    if exclude_keywords:
        for exkw in exclude_keywords:
            buttons.insert(
                -2,
                [
                    InlineKeyboardButton(
                        text=f"❌ {exkw}",
                        callback_data=f"remove_exclude_keywords_{exkw}",
                    )
                ],
            )
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@exclude_keywords_router.callback_query(lambda c: c.data == "edit_exclude_keywords")
async def edit_exclude_keywords(callback: CallbackQuery, state: FSMContext):
    await show_exclude_keywords_menu(callback, state)


@exclude_keywords_router.callback_query(lambda c: c.data == "add_exclude_keywords")
async def add_exclude_keywords_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(FilterForm.waiting_for_input)
    prompt_message = await callback.message.answer(
        "Введите исключающее ключевое слово (или словосочетание):"
    )
    await state.update_data(
        prompt_message_id=prompt_message.message_id, expecting="exclude_keywords"
    )
    await callback.answer()


@exclude_keywords_router.message(FilterForm.waiting_for_input)
async def process_exclude_keywords_input(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("expecting") != "exclude_keywords":
        return
    word = message.text.strip()
    if not word:
        await message.answer("Слово не может быть пустым. Попробуйте ещё раз.")
        return

    prompt_id = data.get("prompt_message_id")
    if prompt_id:
        try:
            await message.bot.delete_message(
                chat_id=message.chat.id, message_id=prompt_id
            )
        except:
            pass

    filters = data.get("filters", {})
    exclude_keywords = filters.get("find_exclude_keywords", [])
    exclude_keywords.append(word)
    filters["find_exclude_keywords"] = exclude_keywords
    await state.update_data(filters=filters, expecting=None)
    await state.set_state(None)

    # Показываем обновлённое меню исключающих слов (отправляем новое сообщение)
    text = "❌ Исключающие ключевые слова:\n" + (
        "\n".join(exclude_keywords) if exclude_keywords else "(пусто)"
    )
    buttons = [
        [
            InlineKeyboardButton(
                text="➕ Добавить слово", callback_data="add_exclude_keywords"
            )
        ],
        [InlineKeyboardButton(text="✅ Готово", callback_data="exclude_keywords_done")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="exclude_keywords_back")],
    ]
    if exclude_keywords:
        for exkw in exclude_keywords:
            buttons.insert(
                -2,
                [
                    InlineKeyboardButton(
                        text=f"❌ {exkw}",
                        callback_data=f"remove_exclude_keywords_{exkw}",
                    )
                ],
            )
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(text, reply_markup=keyboard)


@exclude_keywords_router.callback_query(lambda c: c.data == "exclude_keywords_done")
async def exclude_keywords_done(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    filters = data.get("filters", {})
    await state.update_data(filters=filters)
    keyboard = get_filters_keyboard(filters)
    await callback.message.edit_text("🔍 Настройки фильтрации:", reply_markup=keyboard)
    await state.set_state(None)
    await callback.answer()


@exclude_keywords_router.callback_query(lambda c: c.data == "exclude_keywords_back")
async def exclude_keywords_back(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    filters = data.get("filters", {})
    keyboard = get_filters_keyboard(filters)
    prompt_id = data.get("prompt_message_id")
    if prompt_id:
        try:
            await callback.bot.delete_message(
                chat_id=callback.message.chat.id, message_id=prompt_id
            )
        except:
            pass
    await callback.message.edit_text("🔍 Настройки фильтрации:", reply_markup=keyboard)
    await state.set_state(None)
    await callback.answer()


@exclude_keywords_router.callback_query(
    lambda c: c.data.startswith("remove_exclude_keywords_")
)
async def exclude_keywords_remove(callback: CallbackQuery, state: FSMContext):
    # Извлекаем слово из callback_data (всё, что после префикса)
    word_to_remove = callback.data[len("remove_exclude_keywords_") :]

    data = await state.get_data()
    filters = data.get("filters", {})
    exclude_keywords = filters.get("find_exclude_keywords", [])

    if word_to_remove in exclude_keywords:
        exclude_keywords.remove(word_to_remove)
        filters["find_exclude_keywords"] = exclude_keywords
        await state.update_data(filters=filters)

    # Перерисовываем меню исключающих слов
    await show_exclude_keywords_menu(callback, state)
