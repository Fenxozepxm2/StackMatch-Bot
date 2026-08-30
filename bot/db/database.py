from collections.abc import AsyncGenerator
import json

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.config import load_config

config = load_config()

def custom_json_serializer(*args, **kwargs):
    kwargs['ensure_ascii'] = False  # <--- КЛЮЧЕВОЙ ФЛАГ: отключает \u00xx кодирование
    return json.dumps(*args, **kwargs)


engine = create_async_engine(config.database.url, echo=True, future=True, json_serializer=custom_json_serializer)


Async_Fabric_Session = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def get_session() -> AsyncGenerator:
    async with Async_Fabric_Session() as session:
        yield session
