# bot/keyboard/filter_keyboard.py

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def get_filters_keyboard(data: dict) -> InlineKeyboardMarkup:




    tech_stack_list = data.get("user_tech_stack", [])
    tech_stack_text = ", ".join(tech_stack_list) if tech_stack_list else "не задан"

    # Статус тумблера жесткого отбора по совпадению >= 50%
    strict_stack_status = "🟢 50%+ совпадение" if data.get("strict_stack_filter") else "⚪ Откл"

    # 1. Форматирование города
    city = data.get("city") or "не задан"

    # 2. Форматирование зарплаты и валюты
    salary_from = data.get("salary_from")
    salary_to = data.get("salary_to")
    currency = data.get("currency", "RUR") # Дефолт — рубли
    
    if salary_from or salary_to:
        salary_text = f"{salary_from or '…'} – {salary_to or '…'} {currency}"
    else:
        salary_text = "не задана"

    # 3. Форматирование Стека (Специализации)
    specialization = data.get("specialization") or "не задан"

    # 4. Форматирование Опыта
    exp_val = data.get("exp")
    if exp_val and isinstance(exp_val, list):
        exp_text = ", ".join(exp_val) if exp_val else "не задан"
    else:
        exp_text = "не задан"

    # 5. Форматирование Графика
    schedule_val = data.get("schedule")
    if schedule_val and isinstance(schedule_val, list):
        schedule_text = ", ".join(schedule_val) if schedule_val else "не задан"
    else:
        schedule_text = "не задан"

    # 6. Форматирование Формата работы
    work_format = data.get("workformat")
    if work_format and isinstance(work_format, list):
        work_format_text = ", ".join(work_format) if work_format else "не garbage"
    else:
        work_format_text = "не задан"



    # Собираем чистые, удобные кнопки без лишнего мусора
    buttons = [
        [InlineKeyboardButton(text=f"🏙 Город: {city}", callback_data="edit_city")],
        [
            InlineKeyboardButton(text=f"💰 Зарплата: {salary_text}", callback_data="edit_salary"),
            InlineKeyboardButton(text=f"💱 Валюта: {currency}", callback_data="toggle_currency")
        ],
        [InlineKeyboardButton(text=f"💻 Направление: {specialization}", callback_data="edit_specialization")],
        [InlineKeyboardButton(text=f"🛠 Мой Стек: {tech_stack_text}", callback_data="edit_tech_stack")],
        [InlineKeyboardButton(text=f"🎯 Фильтр по стеку: {strict_stack_status}", callback_data="toggle_strict_stack")],
        [InlineKeyboardButton(text=f"🕒 Опыт: {exp_text}", callback_data="edit_exp")],
        [InlineKeyboardButton(text=f"📅 График: {schedule_text}", callback_data="edit_schedule")],
        [InlineKeyboardButton(text=f"🏢 Формат: {work_format_text}", callback_data="edit_work_format")],
        [InlineKeyboardButton(text=f"✅ Готово", callback_data="close_filters")],
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)
