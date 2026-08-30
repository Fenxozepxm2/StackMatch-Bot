import asyncio


import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, BotCommandScopeDefault
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram.client.session.aiohttp import AiohttpSession

from bot.config import load_config
from bot.handlers import daily_vac, filters, find_vacancies, start_bot, vac_history
from bot.logging_config import setup_logging
from bot.midlewares.for_db import DBSessionMiddleware
from bot.services.city_mapper import CityMapper
from bot.services.send_daily_vac import check_vacancies


async def set_commands(bot: Bot):
    comands = [
        BotCommand(command="start", description="Запустить бота"),
        BotCommand(command="finder", description="поиск вакансий"),
        BotCommand(command="history", description="Избранные вакансии"),
        BotCommand(command="help", description="Получить справку"),
        BotCommand(
            command="show_filters", description="установить обязательные фильтры"
        ),
    ]
    await bot.set_my_commands(comands, scope=BotCommandScopeDefault())


async def on_startup(http_session: aiohttp.ClientSession):
    """Выполняется при старте бота."""
    print("Загрузка справочника городов...")
    await CityMapper.load_cities(http_session)
    print("Справочник городов загружен.")


async def main():
    setup_logging(log_level="DEBUG")

    config = load_config()




    async with aiohttp.ClientSession() as http_session:
        dp = Dispatcher()



        dp.workflow_data["http_session"] = http_session

        aiogram_session = AiohttpSession()

        bot = Bot(
            token=config.bot.token, 
            session=aiogram_session
        )

        dp.update.middleware(DBSessionMiddleware())

        dp.include_router(start_bot.router)
        dp.include_router(filters.router)
        dp.include_router(find_vacancies.router)
        dp.include_router(vac_history.router)
        dp.include_router(daily_vac.router)

        dp.startup.register(on_startup)

        scheduler = AsyncIOScheduler()

        scheduler.add_job(
            check_vacancies, trigger="cron", hour=10, minute=0, kwargs={"bot": bot, "http_session": http_session}
        )
        # scheduler.add_job(
        #     check_vacancies, trigger="interval", minutes=1, kwargs={"bot": bot, "http_session": http_session}
        # )

        scheduler.start()

        await set_commands(bot)
        await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
