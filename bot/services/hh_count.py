"""
Живой счётчик «сколько вакансий найдётся по этим фильтрам».

hh в ответе на поиск всегда отдаёт поле `found` (общее число совпадений), поэтому
достаточно одного лёгкого запроса с per_page=1 — карточки вакансий не качаем.

Защита от тормозов: короткий таймаут и TTL-кэш. Если hh не ответил за пару секунд,
панель всё равно открывается (просто без числа), а повторный клик по тем же фильтрам
отдаётся из кэша мгновенно.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable

import aiohttp
import structlog

from bot.domain.search_filters import SearchFilters

logger = structlog.get_logger(__name__)

HH_VACANCIES_URL = "https://api.hh.ru/vacancies"
USER_AGENT = "StackMatchBot/1.0 (test.example@mail.ru)"

REQUEST_TIMEOUT = 2.5   # сек. на один запрос
CACHE_TTL = 120.0       # сек.
CACHE_MAX_ENTRIES = 512

_cache: dict[tuple, tuple[float, int]] = {}


def _flatten(params: dict[str, Any]) -> list[tuple[str, str]]:
    """{'schedule': ['remote', 'shift']} -> [('schedule','remote'), ('schedule','shift')]"""
    flat: list[tuple[str, str]] = []
    for key, value in params.items():
        if isinstance(value, (list, tuple)):
            flat.extend((key, str(v)) for v in value)
        else:
            flat.append((key, str(value)))
    return flat


async def count_found(
    http_session: aiohttp.ClientSession,
    access_token: str,
    params: dict[str, Any],
) -> int | None:
    """Возвращает `found` или None, если hh не ответил / ответил ошибкой. Исключений не бросает."""
    flat = _flatten({k: v for k, v in params.items() if k not in ("page", "per_page")})
    cache_key = tuple(sorted(flat))

    hit = _cache.get(cache_key)
    if hit and time.monotonic() - hit[0] < CACHE_TTL:
        return hit[1]

    query = [*flat, ("per_page", "1"), ("page", "0")]
    headers = {"User-Agent": USER_AGENT, "Authorization": f"Bearer {access_token}"}
    try:
        async with http_session.get(
            HH_VACANCIES_URL,
            params=query,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
        ) as response:
            if response.status != 200:
                logger.warning("hh_count_bad_status", status=response.status)
                return None
            data = await response.json()
    except (aiohttp.ClientError, asyncio.TimeoutError):
        logger.warning("hh_count_failed", exc_info=True)
        return None

    found = data.get("found")
    if not isinstance(found, int):
        return None

    if len(_cache) >= CACHE_MAX_ENTRIES:
        _cache.clear()
    _cache[cache_key] = (time.monotonic(), found)
    return found


def make_counter(
    http_session: aiohttp.ClientSession,
    access_token: str,
    area_of: Callable[[str], int | str | None] | None = None,
) -> Callable[[SearchFilters], Awaitable[int | None]]:
    """Склеивает домен и hh: SearchFilters -> число вакансий. Именно это передаётся в relax_hints."""

    async def counter(flt: SearchFilters) -> int | None:
        return await count_found(http_session, access_token, flt.to_hh_params(area_of=area_of))

    return counter