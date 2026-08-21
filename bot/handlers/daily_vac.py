import traceback

import structlog
from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputRichMessage,
)
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import *
from bot.db.repos.repo_vacancies import add_vacancy_action
from bot.db.repos.rpeo_notifications import (
    del_top5_vaca_in_notification,
    get_top5_vaca_in_notification,
)

logger = structlog.get_logger(__name__)
router = Router(name="daily_vacancies")


@router.callback_query(F.data == "show_daily_top")
async def send_top5_daily_vac(callback: CallbackQuery, session: AsyncSession):
    try:
        message = callback.message
        tg_id = callback.from_user.id

        top5_vacs = await get_top5_vaca_in_notification(session, tg_id)

        print(" в колбэке вакансии ")
        print(top5_vacs)

        if not top5_vacs:
            logger.info("!!Ошибка!!", tg_id=tg_id, Command="show_daily_top")
            traceback.print_exc()
            return

        # тут мы добавляем в просмотренные
        for vac in top5_vacs:
            await add_vacancy_action(session, tg_id, vac, "view")

        # 2. Перебираем вакансии и отправляем каждую ОТДЕЛЬНЫМ сообщением
        for index, vac in enumerate(top5_vacs, start=1):
            title = vac.get("name")
            url = vac.get("alternate_url")

            # Красивая мини-карточка для каждой вакансии
            html_content = (
                f"<h1>💼 Вакансия №{index}</h1>"
                f"<hr>"
                f"<p><b>Название:</b> <a href='{url}'>{title}</a></p>"
                f"<br>"
                f"<footer>Опубликовано: {vac.get('published_at')[:10]}</footer>"
            )

            rich_message = InputRichMessage(html=html_content)

            # Кнопка удаления, привязанная к ID конкретной вакансии
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🚀 Перейти к вакансии", url=url)]
                ]
            )

            # Отправляем отдельное сообщение
            await message.answer_rich(rich_message=rich_message, reply_markup=keyboard)

        await del_top5_vaca_in_notification(session, tg_id)
        logger.info("Удаление топ-5 вакансий из нотифи", tg_id=tg_id)

    except Exception:
        traceback.print_exc()
        await message.answer("❌ Произошла ошибка при загрузке истории.")
