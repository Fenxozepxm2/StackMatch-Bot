import traceback

import structlog
from aiogram import Bot
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)


import aiohttp
from bot.config import load_config
from bot.db.database import Async_Fabric_Session
from bot.db.repos.repo_filters import get_user_filters
from bot.db.repos.repo_user import get_user, get_all_user_ids
from bot.db.repos.rpeo_notifications import add_top5_vaca_in_notification
from bot.services.to_hhApi import HHAPI, filters_to_params_hh_api

logger = structlog.get_logger(__name__)


config = load_config()


async def check_vacancies(bot: Bot, http_session: aiohttp.ClientSession) -> list:
    """
    проверяет из новых вакансий самые лучшие топ-5 и отправляет пользователю
    каждые 24 часа
    """

    async with Async_Fabric_Session() as bot_session:
        users_ids = await get_all_user_ids(bot_session)

        for tg_id in users_ids:
            try:

                user = await get_user(bot_session, tg_id)

                filters = await get_user_filters(bot_session, tg_id)

                if not filters:
                    continue

                params = await filters_to_params_hh_api(tg_id, bot_session)

                raw_data = await HHAPI.search_vacancies(params, config.access_token.access_token, session=bot_session, http_session=http_session, tg_id=tg_id)

                vacs = raw_data.get("items", [])

                if not vacs:
                    continue

                scored_vacancies = []
                for vac in vacs:
                    score = await HHAPI.personalize_score_safe(
                        vac, user.skills, user.disliked, user.liked
                    )
                    scored_vacancies.append((score, vac))

                scored_vacancies.sort(key=lambda x: x[0], reverse=True)

                top_5_scored = scored_vacancies[:5]

                # список
                top5_vac = [item[1] for item in top_5_scored]

                print("----------- список вакансий в check_vacancies --------------")

                print(top5_vac)

                # тут отправляем пользователю
                if top5_vac:
                    notification_text = (
                        "🎯 <b>Ежедневный подбор</b>\n\n"
                        "<blockquote>"
                        "👋 Привет! Я проанализировал свежие обновления на HeadHunter "
                        "и нашёл <b>5 вакансий</b>, идеально подходящих для вас.\n\n"
                        "</blockquote>"
                    )

                    # Красивая инлайн-кнопка
                    inline_keyboard = InlineKeyboardMarkup(
                        inline_keyboard=[
                            [
                                InlineKeyboardButton(
                                    text="🔎 Показать ТОП-5 подходящих",
                                    callback_data="show_daily_top",
                                )
                            ]
                        ]
                    )

                    # Отправка пользователю
                    await bot.send_message(
                        chat_id=tg_id,
                        text=notification_text,
                        parse_mode="HTML",
                        reply_markup=inline_keyboard,
                    )

                for vac in top5_vac:
                    try:
                        await add_top5_vaca_in_notification(bot_session, tg_id, vac)
                    except Exception:
                        await bot_session.rollback()
                        logger.info("!! ОШИБКА !!" + 
                                    "не удалось добавить уведомления")

            except Exception:
                logger.info("!! ОШИБКА !!", tg_id=tg_id, Command="/test")

                traceback.print_exc()
