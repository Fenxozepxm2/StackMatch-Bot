from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.config import load_config

config = load_config()

engine = create_async_engine(config.database.url, echo=True, future=True)

Async_Fabric_Session = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def get_session() -> AsyncGenerator:
    async with Async_Fabric_Session() as session:
        yield session
