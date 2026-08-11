from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def get_filters_keyboard(data: dict) -> InlineKeyboardMarkup:

    salary_from = data.get("salary_from")
    salary_to = data.get("salary_to")
    if salary_from or salary_to:
        salary_text = f"{salary_from or '…'} – {salary_to or '…'}"
    else:
        salary_text = "не задана"

    schedule_val = data.get("schedule")
    if schedule_val and isinstance(schedule_val, list):
        schedule_text = ", ".join(schedule_val) if schedule_val else "не задан"
    else:
        schedule_text = "не задан"

    exp_val = data.get("exp")
    if exp_val and isinstance(exp_val, list):
        exp_text = ", ".join(exp_val) if exp_val else "не задан"
    else:
        exp_text = "не задан"

    city = data.get("city")

    work_format = data.get("workformat")
    if work_format and isinstance(work_format, list):
        work_format = ", ".join(work_format) if work_format else "не задан"
    else:
        work_format = "не задан"

    specialization = data.get("specialization")

    keywords = ", ".join(data.get("find_key_words", [])) or "не заданы"
    exclude = ", ".join(data.get("find_exclude_keywords", [])) or "не заданы"

    buttons = [
        [InlineKeyboardButton(text=f"🏙 Город: {city}", callback_data="edit_city")],
        [
            InlineKeyboardButton(
                text=f"💰 Зарплата: {salary_text}", callback_data="edit_salary"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"🧠 Специализация: {specialization}",
                callback_data="edit_specialization",
            )
        ],
        [InlineKeyboardButton(text=f"🕒 Опыт: {exp_text}", callback_data="edit_exp")],
        [
            InlineKeyboardButton(
                text=f"📅 График: {schedule_text}", callback_data="edit_schedule"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"🏢 Формат работы: {work_format}",
                callback_data="edit_work_format",
            )
        ],
        [
            InlineKeyboardButton(
                text=f"🔑 Ключевые слова: {keywords}", callback_data="edit_keywords"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"❌ Исключаемые слова: {exclude}", callback_data="edit_exclude"
            )
        ],
        [InlineKeyboardButton(text="✅ Готово", callback_data="close_filters")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
