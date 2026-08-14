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

keywords_router = Router(name="keywords_widget")


async def show_keywords_menu(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    filters = data.get("filters", {})
    keywords = filters.get("find_key_words", [])

    text = "🔑 Ключевые слова:\n" + ("\n".join(keywords) if keywords else "(пусто)")
    buttons = [
        [InlineKeyboardButton(text="➕ Добавить слово", callback_data="add_keyword")],
        [InlineKeyboardButton(text="✅ Готово", callback_data="keywords_done")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="keywords_back")],
    ]
    if keywords:
        # для каждого слова можно добавить кнопку удаления (опционально)
        for kw in keywords:
            buttons.insert(
                -2,
                [
                    InlineKeyboardButton(
                        text=f"❌ {kw}", callback_data=f"remove_keyword_{kw}"
                    )
                ],
            )
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@keywords_router.callback_query(lambda c: c.data == "edit_keywords")
async def edit_keywords(callback: CallbackQuery, state: FSMContext):
    await show_keywords_menu(callback, state)


@keywords_router.callback_query(lambda c: c.data == "add_keyword")
async def add_keyword_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(FilterForm.waiting_for_input)
    promt_message = await callback.message.answer(
        "Введите ключевое слово (или словосочетание):"
    )
    await state.update_data(
        prompt_message_id=promt_message.message_id, expecting="keyword"
    )
    await callback.answer()


@keywords_router.message(FilterForm.waiting_for_input)
async def process_keyword_input(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("expecting") != "keyword":
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
    keywords = filters.get("find_key_words", [])
    keywords.append(word)
    filters["find_key_words"] = keywords
    await state.update_data(filters=filters, expecting=None)
    await state.set_state(None)

     # или show_keywords_menu, но нужно передать callback
    # Удобнее отправить новое меню ключевых слов отдельным сообщением
    buttons = [
        [InlineKeyboardButton(text="➕ Добавить ещё", callback_data="add_keyword")],
        [InlineKeyboardButton(text="✅ Готово", callback_data="keywords_done")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="keywords_back")],
    ]
    kw_text = "\n".join(filters.get("find_key_words", [])) or "(пусто)"
    await message.answer(
        f"🔑 Ключевые слова:\n{kw_text}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await state.set_state(
        FilterForm.waiting_for_input
    )  # остаёмся в режиме ожидания? Нет, сбросим
    await state.set_state(None)


@keywords_router.callback_query(lambda c: c.data == "keywords_done")
async def keywords_done(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    filters = data.get("filters", {})
    await state.update_data(filters=filters)
    keyboard = get_filters_keyboard(filters)
    await callback.message.edit_text("🔍 Настройки фильтрации:", reply_markup=keyboard)
    await state.set_state(None)
    await callback.answer()


@keywords_router.callback_query(lambda c: c.data == "keywords_back")
async def keywords_back(callback: CallbackQuery, state: FSMContext):
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


@keywords_router.callback_query(lambda c: c.data.startswith("remove_keyword_"))
async def keywords_remove(callback: CallbackQuery, state: FSMContext):
    # Извлекаем слово из callback_data (всё, что после префикса)
    word_to_remove = callback.data[len("remove_keyword_") :]

    data = await state.get_data()
    filters = data.get("filters", {})
    keyword = filters.get("find_key_words", [])

    if word_to_remove in keyword:
        keyword.remove(word_to_remove)
        filters["find_key_words"] = keyword
        await state.update_data(filters=filters)

    # Перерисовываем меню исключающих слов
    await show_keywords_menu(callback, state)
