import structlog
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputRichMessage,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import load_config
from bot.db.repos.repo_vacancies import del_fav_vac_from_db, get_favorite_vac

config = load_config()

logger = structlog.get_logger(__name__)

router = Router(name="vacancies_history")


@router.message(Command("history"))
async def show_all_history_messages(
    message: Message, session: AsyncSession, tg_id: int = None
):
    try:

        if tg_id is None:
            tg_id = message.from_user.id

        # 1. Получаем список лайкнутых вакансий из базы
        favorites = await get_favorite_vac(session, tg_id=tg_id)

        if not favorites:
            await message.answer(
                "📋 **Ваш список избранного пока пуст.**\nЛайкайте вакансии в поиске, чтобы они появились здесь!"
            )
            return

        await message.answer(
            f"📦 Загружаю ваши сохраненные вакансии (всего: {len(favorites)})..."
        )

        # 2. Перебираем вакансии и отправляем каждую ОТДЕЛЬНЫМ сообщением
        for index, vac in enumerate(favorites, start=1):
            title = vac.vacancy_title or "Название не указано"
            url = vac.vacancy_url or "https://hh.ru"
            vac_id = vac.vacancy_id

            # Красивая мини-карточка для каждой вакансии
            html_content = (
                f"<h1>💼 Вакансия №{index}</h1>"
                f"<hr>"
                f"<p><b>Название:</b> <a href='{url}'>{title}</a></p>"
                f"<br>"
                f"<footer>Сохранено: {vac.created_at.strftime('%d.%m.%Y %H:%M')}</footer>"
            )

            rich_message = InputRichMessage(html=html_content)

            # Кнопка удаления, привязанная к ID конкретной вакансии
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🗑 Удалить из избранного",
                            callback_data=f"forcedel_{vac_id}",
                        )
                    ]
                ]
            )

            # Отправляем отдельное сообщение
            await message.answer_rich(rich_message=rich_message, reply_markup=keyboard)

    except Exception:
        import traceback

        traceback.print_exc()
        await message.answer("❌ Произошла ошибка при загрузке истории.")


@router.callback_query(lambda c: c.data.startswith("forcedel_"))
async def delete_vac_from_history(callback: CallbackQuery, session: AsyncSession):

    vacan_id = callback.data.split("_")[1].strip()

    await del_fav_vac_from_db(session, callback.from_user.id, vacan_id)

    await callback.answer("Удалено из избранного! 🗑")

    try:
        await callback.message.delete()
    except Exception:
        # Защита на случай, если сообщение старое (старше 48 часов) и Telegram не разрешит его удалить
        await callback.message.edit_text(
            "🗑 _Вакансия была удалена из избранного_", parse_mode="Markdown"
        )
