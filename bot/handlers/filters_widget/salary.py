from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from bot.states.filter_states import FilterForm

salary_router = Router(name="salary_widget")


def normalize_number(raw: str) -> int:
    """
    Преобразует строку с числом в int, игнорируя пробелы, запятые и другие нецифровые символы.
    Примеры: '7 000' -> 7000, '7,000' -> 7000, '7 500' -> 7500
    """
    cleaned = "".join(ch for ch in raw if ch.isdigit())
    if not cleaned:
        raise ValueError("Нет цифр в строке")
    return int(cleaned)


def format_salary(num: int) -> str:
    """Форматирует число с пробелом как разделитель тысяч. Пример: 10000 -> '10 000'"""
    return f"{num:,}".replace(",", " ")


async def show_salary_dialog(callback: CallbackQuery, state: FSMContext):
    """Показывает сообщение с просьбой ввести зарплату и переключает состояние."""
    await state.update_data(expecting="salary")  # помечаем, что ждём зарплату
    await state.set_state(FilterForm.waiting_for_input)
    await callback.message.answer(
        "Введите желаемую зарплату в одном из форматов:\n"
        "• диапазон: 70000 - 120000 (можно с пробелами или запятыми)\n"
        "• только минимальная: от 70000\n"
        "• только максимальная: до 120000\n\n"
        "Примеры: 70 000 - 120 000  или  70000  или  до 100000"
    )
    await callback.answer()


@salary_router.callback_query(lambda c: c.data == "edit_salary")
async def edit_salary_callback(callback: CallbackQuery, state: FSMContext):
    await show_salary_dialog(callback, state)
