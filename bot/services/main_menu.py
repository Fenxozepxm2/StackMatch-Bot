# bot/services/menu_logic.py
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputRichMessage,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession


async def send_main_menu(
    event: Message | CallbackQuery, session: AsyncSession, edit: bool = False
):
    """
    Генерирует и отправляет Главное меню.
    event может быть как Message (от команды /start), так и CallbackQuery (от кнопок).
    """
    # 🎯 ГАРАНТИРОВАННО ПОЛУЧАЕМ ИМЯ РЕАЛЬНОГО ЮЗЕРА, А НЕ БОТА
    if isinstance(event, CallbackQuery):
        user_first_name = event.from_user.first_name
        target_message = event.message  # Сообщение, которое будем редактировать
    else:
        user_first_name = event.from_user.first_name
        target_message = event  # Сообщение, на которое будем отвечать

    # Формируем HTML, используя строго отфильтрованное имя человека
    html_content = (
        f"<h1>🤖 Job Finder Bot</h1>"
        f"<hr>"
        f"<p>Привет, <b>{user_first_name}</b>! Добро пожаловать в интеллектуальный ассистент по поиску работы с системой умного Тиндера.</p>"
        f"<br>"
        f"<blockquote>Бот анализирует ваши лайки и скипы, автоматически подстраивая выдачу под ваши интересы! чем больше вы листаете, тем точнее подборка.</blockquote>"
        f"<br>"
        f"<h3>📍 Доступные инструменты:</h3>"
        f"<p>💼 <b>Поиск</b> — запустить бесконечную ленту вакансий</p>"
        f"<p>🛠 <b>Фильтры</b> — настроить стек, ключевые слова, город и зарплату</p>"
        f"<p>⭐️ <b>Избранное</b> — посмотреть сохраненные вакансии с возможностью удаления</p>"
        f"<p>❓ <b>Справка</b> — руководство по использованию скоринга</p>"
        f"<br>"
        f"<footer>Версия бота: 1.0.4 | База данных: Online</footer>"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💼 Найти вакансии", callback_data="start_search_vacancies"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⚙️ Настройка фильтров", callback_data="menu_open_filters"
                ),
                InlineKeyboardButton(
                    text="⭐️ Избранное (History)", callback_data="menu_open_history"
                ),
            ],
        ]
    )

    rich_message = InputRichMessage(html=html_content)

    if edit:
        # Редактируем сообщение бота, но имя внутри будет человеческое!
        await target_message.edit_text(rich_message=rich_message, reply_markup=keyboard)
    else:
        await target_message.answer_rich(
            rich_message=rich_message, reply_markup=keyboard
        )
