from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


async def build_choice_keyboard(
    options: list,
    current_selection: list,
    toggle_prefix: str,
    save_callback: str,
    cancel_callback: str,
) -> InlineKeyboardMarkup:
    """Универсальная функция для создания клавиатуры множественного выбора."""
    buttons = []
    for opt in options:
        text = f"✅ {opt}" if opt in current_selection else f"➕ {opt}"
        buttons.append(
            [InlineKeyboardButton(text=text, callback_data=f"{toggle_prefix}_{opt}")]
        )
    buttons.append(
        [InlineKeyboardButton(text="💾 Сохранить", callback_data=save_callback)]
    )
    buttons.append(
        [InlineKeyboardButton(text="🔙 Назад", callback_data=cancel_callback)]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)
